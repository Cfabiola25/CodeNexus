"""subsidios-app — registra retiros de afiliados.

Migrado para consumir el nuevo Gateway API con SUBSIDIOS_TOKEN,
manteniendo fallback automático y reversible al procedimiento legacy sp_registrar_retiro.

POST /retiros  {"documento": "...", "fecha": "YYYY-MM-DD", "motivo": "..."}  (puerto 8091)
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg2

logger = logging.getLogger(__name__)

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:8082").rstrip("/")
SUBSIDIOS_TOKEN = os.environ.get("SUBSIDIOS_TOKEN", "")
SUBSIDIOS_MODE = os.environ.get("SUBSIDIOS_MODE", "gateway").lower()


def connect():
    return psycopg2.connect(
        host=os.environ.get("LEGACY_DB_HOST", "legacy-db"),
        port=int(os.environ.get("LEGACY_DB_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "legacy"),
        user=os.environ.get("POSTGRES_USER", "legacy"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        connect_timeout=2,
    )


def registrar_retiro_legacy(documento, fecha, motivo):
    """Camino legacy: invoca sp_registrar_retiro directamente en PostgreSQL."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT sp_registrar_retiro(%s, %s, %s, %s)", (documento, fecha, motivo, "SUBSIDIOS"))
            movimiento = cur.fetchone()[0]
        conn.commit()
        return movimiento
    finally:
        conn.close()


def llamar_gateway_retiro(documento, fecha, motivo, request_id=None):
    """Llama al Gateway API con SUBSIDIOS_TOKEN para registrar el retiro."""
    if not request_id:
        request_id = f"subsidios-{documento}-{int(time.time() * 1000)}"

    url = f"{GATEWAY_URL}/api/v1/members/{documento}/retirements"
    payload = {
        "requestId": request_id,
        "date": fecha,
        "reason": motivo,
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {SUBSIDIOS_TOKEN}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as resp:
        body = resp.read().decode("utf-8")
        resp_data = json.loads(body) if body else {}
        return resp.status, resp_data


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            modo = "legacy" if SUBSIDIOS_MODE == "legacy" else "gateway"
            return self._send(200, {"status": "UP", "modo": modo, "gateway": GATEWAY_URL})
        return self._send(404, {"error": "ruta no encontrada"})

    def do_POST(self):
        if self.path != "/retiros":
            return self._send(404, {"error": "ruta no encontrada"})

        length = int(self.headers.get("Content-Length", "0"))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send(400, {"error": "cuerpo JSON invalido"})

        documento = data.get("documento")
        fecha = data.get("fecha")
        motivo = data.get("motivo", "RETIRO")
        request_id = data.get("requestId")

        if not documento or not fecha:
            return self._send(400, {"error": "documento y fecha son obligatorios"})

        # Si el modo configurado es explícitamente legacy (ej. tras rollback), usar procedimiento directo
        if SUBSIDIOS_MODE == "legacy":
            try:
                movimiento = registrar_retiro_legacy(documento, fecha, motivo)
                return self._send(201, {"movimiento": movimiento, "origen": "legacy"})
            except psycopg2.Error as exc:
                return self._send(500, {"error": str(exc).strip()})

        # Intentar registrar a través del Gateway
        try:
            status, resp_data = llamar_gateway_retiro(documento, fecha, motivo, request_id)
            if status in (200, 201, 202):
                movimiento = resp_data.get("movementId") or resp_data.get("movimiento") or 1
                return self._send(201, {"movimiento": movimiento, "gateway_response": resp_data})
        except urllib.error.HTTPError as exc:
            # Si el Gateway respondió 404 (afiliado no existe), no hacer fallback, reportar error
            if exc.code == 404:
                try:
                    err_payload = json.loads(exc.read().decode("utf-8"))
                except Exception:
                    err_payload = {"error": "afiliado no encontrado"}
                return self._send(404, err_payload)
            # Para errores 5xx del gateway, recurrir a fallback legacy
            logger.warning("Gateway retorno HTTP %d, recurriendo a fallback legacy", exc.code)
        except Exception as exc:
            logger.warning("Error contactando Gateway (%s), recurriendo a fallback legacy", exc)

        # Fallback al procedimiento almacenado legacy
        try:
            movimiento = registrar_retiro_legacy(documento, fecha, motivo)
            return self._send(201, {"movimiento": movimiento, "origen": "legacy_fallback"})
        except psycopg2.Error as exc:
            return self._send(500, {"error": str(exc).strip()})

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8091), Handler).serve_forever()
