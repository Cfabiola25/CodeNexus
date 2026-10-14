"""Configuración de conexión para el adaptador legacy."""

import os
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    host: str = os.environ.get("LEGACY_DB_HOST", "legacy-db")
    port: int = int(os.environ.get("LEGACY_DB_PORT", "5432"))
    database: str = os.environ.get("POSTGRES_DB", "legacy")
    user: str = os.environ.get("POSTGRES_USER", "legacy")
    password: str = os.environ.get("POSTGRES_PASSWORD", "")
    connect_timeout: int = 2  # Menor a 3 segundos para cumplir G10
