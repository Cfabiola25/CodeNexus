"""Capa de adaptación hacia el sistema heredado."""

from .config import DatabaseConfig
from .repository import LegacyRepository

__all__ = ["DatabaseConfig", "LegacyRepository"]
