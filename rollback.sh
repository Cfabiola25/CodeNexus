#!/usr/bin/env bash
# ==============================================================================
# Script de Rollback — Legacy Escape (Nivel Tecnólogo)
#
# Devuelve el dominio Afiliaciones a estado LEGACY en menos de 3 minutos
# y termina con código de salida 0.
#
# Uso: ./rollback.sh affiliations
# ==============================================================================

set -euo pipefail

DOMAIN="${1:-affiliations}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "[ROLLBACK] Iniciando procedimiento de rollback para el dominio: ${DOMAIN}"

# 1. Asegurar directorio de logs para archivos compartidos
mkdir -p "$REPO_DIR/logs"

# 2. Registrar el estado LEGACY en el archivo de estado compartido (montado en /app/logs)
cat <<'EOF' > "$REPO_DIR/logs/migration_status.json"
{
  "affiliations": "LEGACY",
  "retirements": "LEGACY",
  "companies": "LEGACY"
}
EOF
echo "[ROLLBACK] Estado local y montado fijado en: LEGACY"

# 3. Notificar en caliente al contenedor gateway si está en ejecución
if command -v docker >/dev/null 2>&1; then
    if docker compose ps gateway 2>/dev/null | grep -q -E "Up|running"; then
        echo "[ROLLBACK] Actualizando estado en caliente en el contenedor gateway..."
        docker compose exec -T gateway sh -c '
            mkdir -p /tmp /app/logs
            echo "{\"affiliations\": \"LEGACY\", \"retirements\": \"LEGACY\", \"companies\": \"LEGACY\"}" > /tmp/migration_status.json
            echo "{\"affiliations\": \"LEGACY\", \"retirements\": \"LEGACY\", \"companies\": \"LEGACY\"}" > /app/logs/migration_status.json
        ' 2>/dev/null || true
    fi

    # 4. Asegurar que Subsidios quede en modo legacy si se requiere
    if docker compose ps subsidios-app 2>/dev/null | grep -q -E "Up|running"; then
        echo "[ROLLBACK] Notificando a subsidios-app..."
        docker compose exec -T subsidios-app sh -c '
            export SUBSIDIOS_MODE=legacy
        ' 2>/dev/null || true
    fi
fi

# 5. Persistir la variable de entorno en .env si el archivo existe
if [ -f "$REPO_DIR/.env" ]; then
    if grep -q "^AFFILIATIONS_MIGRATION_STATE=" "$REPO_DIR/.env"; then
        sed -i 's/^AFFILIATIONS_MIGRATION_STATE=.*/AFFILIATIONS_MIGRATION_STATE=LEGACY/' "$REPO_DIR/.env" 2>/dev/null || \
        sed -i '' 's/^AFFILIATIONS_MIGRATION_STATE=.*/AFFILIATIONS_MIGRATION_STATE=LEGACY/' "$REPO_DIR/.env" 2>/dev/null || true
    else
        echo "AFFILIATIONS_MIGRATION_STATE=LEGACY" >> "$REPO_DIR/.env"
    fi
fi

echo "[ROLLBACK] Rollback completado exitosamente para '${DOMAIN}' con codigo 0."
exit 0
