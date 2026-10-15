# Plan de migración por dominio

| Dominio | Estado | Criterio para avanzar | Rollback |
|---|---|---|---|
| Afiliaciones | DUAL | 7 días continuos sin diferencias entre gateway y legacy con 0 errores | ./rollback.sh affiliations para retornar a esquema legacy |
| Retiros | LEGACY | 14 días de operación en modo DUAL con 0 retiros perdidos y 100% de reconciliación | Revertir subsidios a sp_registrar_retiro directo |
| Empresas | LEGACY | 30 días sin incidentes y 100% de consultas migradas al gateway | Reconfigurar portal para consulta directa a tabla empresa |

Siguiente dominio: Retiros
