import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from src.api.auth import authenticate_request
from src.utils.audit import record_audit
from src.adapter.legacy_adapter import (
    check_legacy_health,
    find_member_record,
    find_beneficiaries_by_member,
    find_company_detail,
    register_retirement,
)

PORT = int(os.environ.get("GATEWAY_PORT", "8082"))
STATE_FILE_PATH = os.environ.get("MIGRATION_STATE_FILE", "/tmp/migration_status.json")

# Expresiones regulares para enrutamiento seguro
MEMBER_DETAIL_ROUTE = re.compile(r"^/api/v1/members/([0-9A-Za-z_-]+)$")
MEMBER_BENEFICIARIES_ROUTE = re.compile(r"^/api/v1/members/([0-9A-Za-z_-]+)/beneficiaries$")
COMPANY_DETAIL_ROUTE = re.compile(r"^/api/v1/companies/([0-9A-Za-z_-]+)$")
MEMBER_RETIREMENT_ROUTE = re.compile(r"^/api/v1/members/([0-9A-Za-z_-]+)/retirements$")


def get_current_migration_state() -> str:
    """Lee el estado del dominio de afiliaciones (controlado por rollback.sh o variable de entorno)."""
    env_state = os.environ.get("AFFILIATIONS_MIGRATION_STATE")
    if env_state:
        return env_state.strip().upper()
    if os.path.exists(STATE_FILE_PATH):
        try:
            with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("affiliations", "DUAL")
        except Exception:
            pass
    return "DUAL"


class GatewayRequestHandler(BaseHTTPRequestHandler):
    def _send_response(self, status_code: int, payload: dict, started_at: float, consumer: str = "unknown"):
        latency_ms = (time.time() - started_at) * 1000.0
        body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

        # Registro en logs/audit.log
        record_audit(consumer, self.path, status_code, latency_ms)

    def _handle_error(self, status_code: int, message: str, error_id: str, started_at: float, consumer: str = "unknown"):
        payload = {
            "message": message,
            "error_id": error_id,
        }
        self._send_response(status_code, payload, started_at, consumer)

    def _handle_legacy_unavailable(self, started_at: float, consumer: str = "unknown"):
        payload = {
            "code": "LEGACY_UNAVAILABLE",
            "message": "El servicio de datos heredado no responde en el limite de tiempo",
            "error_id": "ERR-LEGACY-503",
        }
        self._send_response(503, payload, started_at, consumer)

    def do_GET(self):
        started_at = time.time()
        path = self.path.split("?")[0].rstrip("/")

        # Ruta 1: /health (sin requerimiento de token segun contrato)
        if path == "/health":
            legacy_online = check_legacy_health()
            payload = {
                "status": "UP",
                "legacy": "UP" if legacy_online else "DOWN",
            }
            return self._send_response(200, payload, started_at, consumer="portal")

        # Validacion de autenticacion para rutas protegidas
        is_valid, consumer, error_dict, status_code = authenticate_request(self.headers, "GET")
        if not is_valid:
            return self._send_response(status_code, error_dict, started_at, consumer=consumer or "unknown")

        # Ruta 2: /api/v1/migration/status
        if path == "/api/v1/migration/status":
            current_state = get_current_migration_state()
            payload = {
                "domains": {
                    "affiliations": current_state,
                    "retirements": "LEGACY",
                    "companies": "LEGACY",
                }
            }
            return self._send_response(200, payload, started_at, consumer=consumer)

        # Ruta 3: /api/v1/members/{document}/beneficiaries
        match_ben = MEMBER_BENEFICIARIES_ROUTE.match(path)
        if match_ben:
            document_id = match_ben.group(1)
            try:
                # Comprobar primero existencia del titular
                member = find_member_record(document_id)
                if not member:
                    return self._handle_error(404, f"Afiliado {document_id} no registrado", "ERR-MEMBER-404", started_at, consumer)

                beneficiaries = find_beneficiaries_by_member(document_id)
                return self._send_response(200, beneficiaries, started_at, consumer=consumer)
            except Exception:
                return self._handle_legacy_unavailable(started_at, consumer)

        # Ruta 4: /api/v1/members/{document}
        match_member = MEMBER_DETAIL_ROUTE.match(path)
        if match_member:
            document_id = match_member.group(1)
            try:
                member = find_member_record(document_id)
                if not member:
                    return self._handle_error(404, f"Afiliado {document_id} no existe", "ERR-MEMBER-404", started_at, consumer)
                return self._send_response(200, member, started_at, consumer=consumer)
            except Exception:
                return self._handle_legacy_unavailable(started_at, consumer)

        # Ruta 5: /api/v1/companies/{id}
        match_company = COMPANY_DETAIL_ROUTE.match(path)
        if match_company:
            company_id = match_company.group(1)
            try:
                company = find_company_detail(company_id)
                if not company:
                    return self._handle_error(404, f"Empresa {company_id} no encontrada", "ERR-COMPANY-404", started_at, consumer)
                return self._send_response(200, company, started_at, consumer=consumer)
            except Exception:
                return self._handle_legacy_unavailable(started_at, consumer)

        return self._handle_error(404, "Endpoint no encontrado en la API", "ERR-NOT-FOUND-404", started_at, consumer)

    def do_POST(self):
        started_at = time.time()
        path = self.path.split("?")[0].rstrip("/")

        # Validacion de autenticacion y control de permisos de escritura
        is_valid, consumer, error_dict, status_code = authenticate_request(self.headers, "POST")
        if not is_valid:
            return self._send_response(status_code, error_dict, started_at, consumer=consumer or "unknown")

        # Ruta 6: /api/v1/members/{document}/retirements
        match_ret = MEMBER_RETIREMENT_ROUTE.match(path)
        if match_ret:
            document_id = match_ret.group(1)
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_len) if content_len > 0 else b"{}"
                data = json.loads(raw_body.decode("utf-8"))
            except Exception:
                return self._handle_error(400, "Cuerpo JSON invalido", "ERR-BAD-REQUEST-400", started_at, consumer)

            request_id = data.get("requestId", "").strip()
            effective_date = data.get("date", "").strip()
            reason = data.get("reason", "RETIRO").strip()

            if not request_id or not effective_date:
                return self._handle_error(400, "Los campos requestId y date son obligatorios", "ERR-PARAMS-400", started_at, consumer)

            try:
                # Comprobar que el afiliado exista
                member = find_member_record(document_id)
                if not member:
                    return self._handle_error(404, f"Afiliado {document_id} no existe", "ERR-MEMBER-404", started_at, consumer)

                movement_id, is_new = register_retirement(
                    document_id=document_id,
                    effective_date=effective_date,
                    reason=reason,
                    request_id=request_id,
                    user_id="SUBSIDIOS" if consumer == "subsidios" else "GATEWAY"
                )

                response_status = 201 if is_new else 200
                payload = {
                    "status": "PROCESSED" if is_new else "ALREADY_PROCESSED",
                    "message": "Retiro registrado correctamente" if is_new else "Solicitud procesada con anterioridad",
                    "movementId": movement_id,
                }
                return self._send_response(response_status, payload, started_at, consumer=consumer)
            except Exception as exc:
                err_msg = str(exc)
                if "404" in err_msg:
                    return self._handle_error(404, f"Afiliado {document_id} no existe", "ERR-MEMBER-404", started_at, consumer)
                return self._handle_legacy_unavailable(started_at, consumer)

        return self._handle_error(404, "Endpoint de escritura no encontrado", "ERR-NOT-FOUND-404", started_at, consumer)

    def log_message(self, fmt, *args):
        # Evitar imprimir en stderr por cada solicitud para mantener los logs limpios
        return


def run_server():
    server_address = ("0.0.0.0", PORT)
    httpd = ThreadingHTTPServer(server_address, GatewayRequestHandler)
    print(f"[GATEWAY] Capa de transicion activa en el puerto {PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()
