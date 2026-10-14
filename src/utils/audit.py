import json
import os
import re
import time
from datetime import datetime, timezone

LOGS_DIR = os.environ.get("LOGS_DIR", "logs")
AUDIT_LOG_PATH = os.path.join(LOGS_DIR, "audit.log")

DIGITS_REGEX = re.compile(r"\b(\d{5,})\b")


def mask_document(document: str) -> str:
    """Enmascara un documento permitiendo ver como maximo los ultimos 4 digitos."""
    clean = str(document).strip()
    if len(clean) <= 4:
        return clean
    return "*" * (len(clean) - 4) + clean[-4:]


def mask_endpoint(endpoint: str) -> str:
    """Enmascara secuencias de digitos largas en la ruta para evitar exponer documentos."""
    return DIGITS_REGEX.sub(lambda m: mask_document(m.group(1)), endpoint)


def record_audit(consumer: str, endpoint: str, status: int, latency_ms: float) -> None:
    """Registra una entrada estructurada de auditoria en logs/audit.log."""
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    except OSError:
        pass

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "consumer": consumer,
        "endpoint": mask_endpoint(endpoint),
        "status": status,
        "latency_ms": round(latency_ms, 2),
    }

    line = json.dumps(entry, ensure_ascii=False) + "\n"
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as exc:
        # En caso de error de I/O en logs, no interrumpir el flujo principal
        print(f"[AUDIT ERROR] No se pudo escribir en {AUDIT_LOG_PATH}: {exc}")
