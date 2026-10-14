"""Repositorio SQL hacia PostgreSQL del sistema legacy.

Regla de oro: Este archivo es el ÚNICO lugar del código que conoce nombres
y esquemas heredados como AFI_MAE, NRO_DOC, PERSON_MASTER, DOCUMENT_NUMBER,
STATUS_CODE, AFI_BEN, EMPRESA, LOGMOV y sp_registrar_retiro.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2 import OperationalError, errors

from src.adapter.config import DatabaseConfig
from src.core.exceptions import EntityNotFoundError, ServiceUnavailableError
from src.core.models import (
    Beneficiary,
    Company,
    CompanySummary,
    Member,
    RetirementResult,
)

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "A": "ACTIVE",
    "R": "RETIRED",
    "S": "SUSPENDED",
}

RELATIONSHIP_MAP = {
    "C": "CONYUGE",
    "H": "HIJO",
    "P": "PADRE",
    "M": "MADRE",
}


class LegacyRepository:
    """Adaptador de base de datos para la base heredada Informix/PostgreSQL."""

    def __init__(self, config: Optional[DatabaseConfig] = None, storage_dir: Optional[str] = None):
        self.config = config or DatabaseConfig()
        base_dir = Path(storage_dir or os.environ.get("DATA_DIR", "./data"))
        base_dir.mkdir(parents=True, exist_ok=True)
        self.idempotency_file = base_dir / "idempotency.json"
        self.pending_file = base_dir / "pending_retirements.json"

        self._idempotency_cache: Dict[str, Any] = self._load_json(self.idempotency_file)
        self._pending_retirements: List[Dict[str, Any]] = self._load_json(self.pending_file, default=[])

    def _load_json(self, path: Path, default: Any = None) -> Any:
        if default is None:
            default = {}
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json(self, path: Path, data: Any) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Error guardando archivo %s: %s", path, exc)

    def _get_connection(self):
        """Abre conexión con timeout estricto < 3s para cumplir G10."""
        try:
            return psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                dbname=self.config.database,
                user=self.config.user,
                password=self.config.password,
                connect_timeout=self.config.connect_timeout,
            )
        except OperationalError as exc:
            raise ServiceUnavailableError("No se pudo conectar a legacy-db") from exc

    def check_health(self) -> bool:
        """Verifica si la base de datos legacy está disponible."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    return cur.fetchone() is not None
        except Exception:
            return False

    def _get_schema_metadata(self, conn) -> Tuple[str, str, str]:
        """Detecta dinámicamente si el esquema ya fue modificado por schema-change.sh."""
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.person_master') IS NOT NULL;")
            has_person_master = cur.fetchone()[0]

        if has_person_master:
            return "person_master", "document_number", "status_code"
        return "afi_mae", "nro_doc", "est_afi"

    def get_member(self, document: str) -> Member:
        """Consulta un afiliado por documento y lo retorna en modelo canónico."""
        conn = self._get_connection()
        try:
            table_name, doc_col, status_col = self._get_schema_metadata(conn)
            query = f"""
                SELECT m.{doc_col}, m.nom1, m.nom2, m.ape1, m.ape2, m.{status_col},
                       e.cod_emp, e.nom_emp
                FROM {table_name} m
                LEFT JOIN empresa e ON e.cod_emp = m.cod_emp
                WHERE m.{doc_col} = %s
            """
            with conn.cursor() as cur:
                cur.execute(query, (document,))
                row = cur.fetchone()

            if not row:
                raise EntityNotFoundError(f"Afiliado con documento {document} no encontrado")

            doc_val, nom1, nom2, ape1, ape2, status_raw, cod_emp, nom_emp = row
            full_name = " ".join(part.strip() for part in [nom1, nom2, ape1, ape2] if part and part.strip())
            canonical_status = STATUS_MAP.get(str(status_raw).strip(), "ACTIVE")

            company_summary = CompanySummary(
                id=str(cod_emp or "").strip(),
                name=str(nom_emp or "").strip(),
            )

            return Member(
                document=str(doc_val).strip(),
                fullName=full_name,
                status=canonical_status,
                company=company_summary,
            )
        except OperationalError as exc:
            raise ServiceUnavailableError("Fallo de comunicación con legacy-db") from exc
        finally:
            conn.close()

    def get_beneficiaries(self, document: str) -> List[Beneficiary]:
        """Consulta los beneficiarios de un afiliado en modelo canónico."""
        conn = self._get_connection()
        try:
            query = """
                SELECT nro_doc_ben, nom1, nom2, ape1, ape2, cod_par
                FROM afi_ben
                WHERE nro_doc = %s
                ORDER BY nro_doc_ben
            """
            with conn.cursor() as cur:
                cur.execute(query, (document,))
                rows = cur.fetchall()

            beneficiaries = []
            for row in rows:
                doc_ben, nom1, nom2, ape1, ape2, cod_par = row
                full_name = " ".join(part.strip() for part in [nom1, nom2, ape1, ape2] if part and part.strip())
                relationship = RELATIONSHIP_MAP.get(str(cod_par).strip(), str(cod_par).strip())

                beneficiaries.append(
                    Beneficiary(
                        document=str(doc_ben).strip(),
                        fullName=full_name,
                        relationship=relationship,
                    )
                )
            return beneficiaries
        except OperationalError as exc:
            raise ServiceUnavailableError("Fallo de comunicación con legacy-db") from exc
        finally:
            conn.close()

    def get_company(self, company_id: str) -> Company:
        """Consulta información de una empresa y calcula miembros activos."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT cod_emp, nom_emp FROM empresa WHERE cod_emp = %s", (company_id,))
                row = cur.fetchone()

            if not row:
                raise EntityNotFoundError(f"Empresa {company_id} no encontrada")

            cod_emp, nom_emp = row
            table_name, _, status_col = self._get_schema_metadata(conn)

            count_query = f"SELECT count(*) FROM {table_name} WHERE cod_emp = %s AND {status_col} = 'A'"
            with conn.cursor() as cur:
                cur.execute(count_query, (company_id,))
                active_count = cur.fetchone()[0]

            return Company(
                id=str(cod_emp).strip(),
                name=str(nom_emp).strip(),
                activeMembers=int(active_count or 0),
            )
        except OperationalError as exc:
            raise ServiceUnavailableError("Fallo de comunicación con legacy-db") from exc
        finally:
            conn.close()

    def register_retirement(
        self,
        document: str,
        date: str,
        reason: str,
        request_id: str,
        consumer: str = "SUBSIDIOS",
    ) -> RetirementResult:
        """Registra el retiro de un afiliado de forma idempotente con fallback en caída."""
        # 1. Comprobar idempotencia en caché
        if request_id in self._idempotency_cache:
            cached = self._idempotency_cache[request_id]
            return RetirementResult(
                requestId=request_id,
                status=cached.get("status", "COMPLETED"),
                isDuplicate=True,
                movementId=cached.get("movementId"),
            )

        # 2. Intentar ejecutar en base de datos
        try:
            conn = self._get_connection()
        except ServiceUnavailableError:
            # Tolerancia a caídas del legacy (G11): aceptar retiro temporalmente (202 Accepted)
            pending_record = {
                "document": document,
                "date": date,
                "reason": reason,
                "requestId": request_id,
                "consumer": consumer,
            }
            self._pending_retirements.append(pending_record)
            self._save_json(self.pending_file, self._pending_retirements)
            return RetirementResult(
                requestId=request_id,
                status="ACCEPTED",
                isDuplicate=False,
                movementId=None,
            )

        try:
            with conn:
                with conn.cursor() as cur:
                    # Validar si el afiliado existe
                    table_name, doc_col, _ = self._get_schema_metadata(conn)
                    cur.execute(f"SELECT 1 FROM {table_name} WHERE {doc_col} = %s", (document,))
                    if not cur.fetchone():
                        raise EntityNotFoundError(f"Afiliado {document} no existe")

                    # Ejecutar procedimiento legacy sp_registrar_retiro
                    cur.execute(
                        "SELECT sp_registrar_retiro(%s, %s, %s, %s)",
                        (document, date, f"{reason} [{request_id}]", consumer),
                    )
                    movement_id = cur.fetchone()[0]

            # Registrar en almacén de idempotencia
            result_data = {"status": "COMPLETED", "movementId": movement_id}
            self._idempotency_cache[request_id] = result_data
            self._save_json(self.idempotency_file, self._idempotency_cache)

            return RetirementResult(
                requestId=request_id,
                status="COMPLETED",
                isDuplicate=False,
                movementId=movement_id,
            )
        except errors.RaiseException as exc:
            if "AFI-404" in str(exc):
                raise EntityNotFoundError(f"Afiliado {document} no existe") from exc
            raise
        except OperationalError as exc:
            raise ServiceUnavailableError("Fallo de conexión al registrar retiro") from exc
        finally:
            conn.close()

    def sync_pending_retirements(self) -> int:
        """Procesa retiros que hayan quedado encolados durante una caída del legacy."""
        if not self._pending_retirements or not self.check_health():
            return 0

        synced = 0
        remaining = []
        for item in self._pending_retirements:
            req_id = item["requestId"]
            if req_id in self._idempotency_cache:
                continue
            try:
                res = self.register_retirement(
                    document=item["document"],
                    date=item["date"],
                    reason=item["reason"],
                    request_id=req_id,
                    consumer=item.get("consumer", "SUBSIDIOS"),
                )
                if res.status == "COMPLETED":
                    synced += 1
                else:
                    remaining.append(item)
            except Exception as exc:
                logger.error("Error sincronizando retiro pendiente %s: %s", req_id, exc)
                remaining.append(item)

        self._pending_retirements = remaining
        self._save_json(self.pending_file, self._pending_retirements)
        return synced
