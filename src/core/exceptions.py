"""Excepciones de dominio canónico.

No contiene referencias a bases de datos heredadas ni nombres de tablas del sistema legacy.
"""


class DomainError(Exception):
    """Error base de dominio."""
    def __init__(self, message: str, error_id: str = "DOMAIN_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_id = error_id


class EntityNotFoundError(DomainError):
    """Entidad no encontrada en el sistema."""
    def __init__(self, message: str = "Recurso no encontrado", error_id: str = "NOT_FOUND"):
        super().__init__(message, error_id)


class ServiceUnavailableError(DomainError):
    """Servicio de persistencia no disponible."""
    def __init__(self, message: str = "Servicio de persistencia no disponible", error_id: str = "LEGACY_UNAVAILABLE"):
        super().__init__(message, error_id)


class ConflictError(DomainError):
    """Conflicto en la operación de dominio."""
    def __init__(self, message: str = "Conflicto en la solicitud", error_id: str = "CONFLICT"):
        super().__init__(message, error_id)
