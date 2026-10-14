import os
from typing import Optional, Tuple

CONSUMER_PORTAL = "portal"
CONSUMER_SUBSIDIOS = "subsidios"
CONSUMER_MOBILE = "mobile"


def get_token_map() -> dict:
    """Obtiene el mapeo de tokens configurados hacia nombres canonicos de consumidores."""
    return {
        os.environ.get("PORTAL_TOKEN", "portal-secret"): CONSUMER_PORTAL,
        os.environ.get("SUBSIDIOS_TOKEN", "subsidios-secret"): CONSUMER_SUBSIDIOS,
        os.environ.get("MOBILE_TOKEN", "mobile-secret"): CONSUMER_MOBILE,
    }


def authenticate_request(headers, http_method: str) -> Tuple[bool, Optional[str], Optional[dict], int]:
    """
    Valida el encabezado Authorization: Bearer <token>.
    Retorna: (is_valid, consumer_name, error_dict, http_status_code)
    """
    auth_header = headers.get("Authorization", "").strip()
    if not auth_header:
        return False, None, {
            "message": "Encabezado de autorizacion requerido",
            "error_id": "ERR-AUTH-401"
        }, 401

    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False, None, {
            "message": "Esquema de autenticacion invalido. Se espera Bearer <token>",
            "error_id": "ERR-AUTH-401"
        }, 401

    token = parts[1].strip()
    token_map = get_token_map()
    consumer = token_map.get(token)

    if not consumer:
        return False, None, {
            "message": "Token de autenticacion invalido o revocado",
            "error_id": "ERR-AUTH-401"
        }, 401

    # Regla de privilegios: el consumidor movil solo tiene permisos de lectura
    if consumer == CONSUMER_MOBILE and http_method.upper() != "GET":
        return False, consumer, {
            "message": "El consumidor movil solo dispone de privilegios de consulta",
            "error_id": "ERR-PERM-403"
        }, 403

    return True, consumer, None, 200
