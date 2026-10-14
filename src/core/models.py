"""Modelo canónico limpio.

Representa las entidades del dominio sin acoplamiento a esquemas legacy.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class CompanySummary:
    """Resumen de la empresa asociada a un afiliado."""
    id: str
    name: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Company:
    """Detalle completo de una empresa."""
    id: str
    name: str
    activeMembers: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Beneficiary:
    """Beneficiario de un afiliado."""
    document: str
    fullName: str
    relationship: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Member:
    """Afiliado principal del sistema."""
    document: str
    fullName: str
    status: str
    company: CompanySummary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document": self.document,
            "fullName": self.fullName,
            "status": self.status,
            "company": self.company.to_dict(),
        }


@dataclass
class RetirementRequest:
    """Solicitud de retiro de un afiliado."""
    requestId: str
    document: str
    date: str
    reason: str


@dataclass
class RetirementResult:
    """Resultado del procesamiento de un retiro."""
    requestId: str
    status: str
    isDuplicate: bool = False
    movementId: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "requestId": self.requestId,
            "status": self.status,
        }
        if self.movementId is not None:
            result["movementId"] = self.movementId
        return result
