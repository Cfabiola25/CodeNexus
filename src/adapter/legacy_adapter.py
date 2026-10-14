"""
Adaptador de persistencia hacia la base de datos heredada (PostgreSQL / Informix).
REGLA ARQUITECTONICA OBLIGATORIA (GE01):
Este archivo y esta carpeta 'adapter' es el UNICO lugar del repositorio
donde esta permitido hacer referencia a tablas, columnas y procedimientos legacy:
AFI_MAE, NRO_DOC, EST_AFI, COD_EMP, NOM_EMP, COD_PAR, NRO_DOC_BEN,
PERSON_MASTER, DOCUMENT_NUMBER, STATUS_CODE, SP_REGISTRAR_RETIRO, LOGMOV.
"""

import os
from typing import Dict, List, Optional, Tuple
import psycopg2


def get_connection():
    """Establece conexion con la base legacy con timeout estricto de 2 segundos."""
    return psycopg2.connect(
        host=os.environ.get("LEGACY_DB_HOST", "legacy-db"),
        port=int(os.environ.get("LEGACY_DB_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "legacy"),
        user=os.environ.get("POSTGRES_USER", "legacy"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        connect_timeout=2,
    )


def check_legacy_health() -> bool:
    """Comprueba la disponibilidad operativa del motor de base de datos."""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        finally:
            conn.close()
    except Exception:
        return False


def build_full_name(first_name: Optional[str], second_name: Optional[str],
                    last_name: Optional[str], second_last_name: Optional[str]) -> str:
    """Concatena de forma limpia los componentes del nombre."""
    parts = [first_name, second_name, last_name, second_last_name]
    return " ".join(p.strip() for p in parts if p and p.strip())


def normalize_status(code: Optional[str]) -> str:
    """Mapea los codigos de estado heredados a enumeraciones canonicas."""
    mapping = {
        "A": "ACTIVE",
        "R": "RETIRED",
        "S": "SUSPENDED",
    }
    return mapping.get((code or "").strip().upper(), "SUSPENDED")


def normalize_relationship(code: Optional[str]) -> str:
    """Mapea codigos de parentesco heredados."""
    mapping = {
        "C": "CONYUGE",
        "H": "HIJO",
        "P": "PADRE",
        "M": "MADRE",
    }
    return mapping.get((code or "").strip().upper(), "BENEFICIARIO")


def find_member_record(document_id: str) -> Optional[dict]:
    """
    Consulta un afiliado soportando resiliencia ante el evento de cambio de esquema:
    AFI_MAE(nro_doc, est_afi) o PERSON_MASTER(document_number, status_code).
    """
    conn = get_connection()
    conn.autocommit = True
    queries = [
        # Esquema original
        """
        SELECT a.nro_doc, a.nom1, a.nom2, a.ape1, a.ape2, a.est_afi, a.cod_emp, e.nom_emp
          FROM afi_mae a
          LEFT JOIN empresa e ON e.cod_emp = a.cod_emp
         WHERE a.nro_doc = %s
        """,
        # Esquema moderno tras cambio de esquema del DBA
        """
        SELECT a.document_number, a.nom1, a.nom2, a.ape1, a.ape2, a.status_code, a.cod_emp, e.nom_emp
          FROM person_master a
          LEFT JOIN empresa e ON e.cod_emp = a.cod_emp
         WHERE a.document_number = %s
        """,
    ]

    try:
        for sql in queries:
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, (document_id,))
                    row = cur.fetchone()
                    if row:
                        doc, nom1, nom2, ape1, ape2, estado, cod_emp, nom_emp = row
                        return {
                            "document": str(doc).strip(),
                            "fullName": build_full_name(nom1, nom2, ape1, ape2),
                            "status": normalize_status(estado),
                            "company": {
                                "id": str(cod_emp or "").strip(),
                                "name": str(nom_emp or "").strip(),
                            },
                        }
                    # Si ejecuto sin error y no encontro fila, no es error de esquema
                    return None
            except psycopg2.errors.UndefinedTable:
                continue
            except psycopg2.errors.UndefinedColumn:
                continue
        return None
    finally:
        conn.close()


def find_beneficiaries_by_member(document_id: str) -> List[dict]:
    """Consulta la lista de beneficiarios asociados a un afiliado."""
    conn = get_connection()
    conn.autocommit = True
    sql = """
    SELECT b.nro_doc_ben, b.nom1, b.nom2, b.ape1, b.ape2, b.cod_par
      FROM afi_ben b
     WHERE b.nro_doc = %s
     ORDER BY b.nro_doc_ben
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (document_id,))
            rows = cur.fetchall()
            results = []
            for row in rows:
                doc_ben, nom1, nom2, ape1, ape2, cod_par = row
                results.append({
                    "document": str(doc_ben).strip(),
                    "fullName": build_full_name(nom1, nom2, ape1, ape2),
                    "relationship": normalize_relationship(cod_par),
                })
            return results
    finally:
        conn.close()


def find_company_detail(company_id: str) -> Optional[dict]:
    """Consulta la razon social y el conteo de miembros activos de una empresa."""
    conn = get_connection()
    conn.autocommit = True
    sql_company = "SELECT cod_emp, nom_emp FROM empresa WHERE cod_emp = %s"
    count_queries = [
        "SELECT COUNT(*) FROM afi_mae WHERE cod_emp = %s AND est_afi = 'A'",
        "SELECT COUNT(*) FROM person_master WHERE cod_emp = %s AND status_code = 'A'",
    ]

    try:
        with conn.cursor() as cur:
            cur.execute(sql_company, (company_id,))
            comp_row = cur.fetchone()
            if not comp_row:
                return None
            cod_emp, nom_emp = comp_row

        active_count = 0
        for count_sql in count_queries:
            try:
                with conn.cursor() as cur:
                    cur.execute(count_sql, (company_id,))
                    res = cur.fetchone()
                    if res:
                        active_count = int(res[0])
                        break
            except psycopg2.errors.UndefinedTable:
                continue
            except psycopg2.errors.UndefinedColumn:
                continue

        return {
            "id": str(cod_emp).strip(),
            "name": str(nom_emp).strip(),
            "activeMembers": active_count,
        }
    finally:
        conn.close()


# Cache de solicitudes procesadas para garantizar idempotencia estricta
_PROCESSED_REQUESTS: Dict[str, int] = {}


def register_retirement(document_id: str, effective_date: str, reason: str,
                        request_id: str, user_id: str = "SUBSIDIOS") -> Tuple[int, bool]:
    """
    Registra el retiro invocando sp_registrar_retiro.
    Retorna (movement_id, is_new):
    Si el request_id ya fue procesado, retorna el movement_id previo con is_new = False.
    """
    if request_id in _PROCESSED_REQUESTS:
        return _PROCESSED_REQUESTS[request_id], False

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Primero verificar si el request_id ya fue asentado en logmov
            cur.execute(
                "SELECT id_mov FROM logmov WHERE nro_doc = %s AND obs_mov LIKE %s LIMIT 1",
                (document_id, f"%{request_id}%")
            )
            existing = cur.fetchone()
            if existing:
                _PROCESSED_REQUESTS[request_id] = existing[0]
                return existing[0], False

            obs_text = f"[{request_id}] {reason}".strip()[:200]
            cur.execute("SELECT sp_registrar_retiro(%s, %s, %s, %s)",
                        (document_id, effective_date, obs_text, user_id))
            movement_id = cur.fetchone()[0]

        conn.commit()
        _PROCESSED_REQUESTS[request_id] = movement_id
        return movement_id, True
    finally:
        conn.close()
