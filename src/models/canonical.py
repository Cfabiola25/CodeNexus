from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class CompanySummary:
    id: str
    name: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MemberProfile:
    document: str
    fullName: str
    status: str  # "ACTIVE", "RETIRED", "SUSPENDED"
    company: CompanySummary

    def to_dict(self) -> dict:
        return {
            "document": self.document,
            "fullName": self.fullName,
            "status": self.status,
            "company": self.company.to_dict(),
        }


@dataclass
class BeneficiaryProfile:
    document: str
    fullName: str
    relationship: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompanyProfile:
    id: str
    name: str
    activeMembers: int

    def to_dict(self) -> dict:
        return asdict(self)
