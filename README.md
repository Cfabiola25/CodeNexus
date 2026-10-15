# Legacy Escape — Nelly Cano & Nick Ortega

## Descripción

Solución de modernización progresiva para la plataforma tecnológica de la Caja de Compensación Familiar mediante el patrón Strangler Fig. Permite evolucionar el sistema heredado sin suspender la operación del negocio ni romper las aplicaciones dependientes, construyendo una capa intermedia de transición (API Gateway, modelo canónico y adaptador de persistencia) que encapsula las estructuras relacionales de la base legacy, asegura el control de acceso basado en tokens por consumidor, registra auditoría con privacidad de datos y ofrece un plan de migración por dominios con reversibilidad comprobada.

## Integrantes

- Nelly Fabiola Cano Oviedo
- Nick Ortega

## Requisitos

Para desplegar y validar la solución se requiere contar con Docker Engine 24.0+, Docker Compose v2, Python 3.10+ y utilidades estándar de terminal Linux/Unix como bash, curl, jq y psql.

## Instalación y ejecución

Para levantar el entorno completo desde una copia limpia del repositorio, ejecute en orden los siguientes comandos:

```bash
cp .env.example .env
docker compose up -d --build
```

En caso de requerir devolver el dominio de Afiliaciones al estado operacional legacy de contingencia, ejecute:

```bash
./rollback.sh affiliations
```

## Configuración

Las variables de entorno requeridas se definen en el archivo `.env.example`:

- `POSTGRES_DB`: Nombre de la base de datos relacional PostgreSQL del sistema legacy (ejemplo: `legacy`).
- `POSTGRES_USER`: Usuario con privilegios de conexión sobre la base de datos (ejemplo: `legacy`).
- `POSTGRES_PASSWORD`: Contraseña para autenticar la conexión a la base de datos (ejemplo: `legacy`).
- `LEGACY_DB_HOST`: Host o nombre del servicio de base de datos en la red interna de contenedores (ejemplo: `legacy-db`).
- `LEGACY_DB_PORT`: Puerto de escucha de la base de datos PostgreSQL (ejemplo: `5432`).
- `GATEWAY_URL`: Dirección base del API Gateway empleada por las aplicaciones para comunicación HTTP (ejemplo: `http://gateway:8082`).
- `PORTAL_TOKEN`: Token secreto Bearer asignado al cliente del portal web para consultas (ejemplo: `portal-secret`).
- `SUBSIDIOS_TOKEN`: Token secreto Bearer otorgado a la aplicación de subsidios para trámites de retiro (ejemplo: `subsidios-secret`).
- `MOBILE_TOKEN`: Token secreto Bearer asignado a la app móvil con permisos de solo lectura (ejemplo: `mobile-secret`).

## Arquitectura

La solución implementa una arquitectura desacoplada donde ninguna aplicación nueva accede de forma directa a la base heredada. En `docker-compose.yml` se orquestan los siguientes servicios interconectados:

- `legacy-db`: Motor de base de datos PostgreSQL que aloja el esquema heredado y los procedimientos almacenados transaccionales.
- `educacion-app`: Aplicación histórica que continúa leyendo directamente la base de datos sin requerir modificaciones.
- `portal-client`: Nuevo portal de servicios que consulta información exclusivamente consumiendo el Gateway por HTTP.
- `subsidios-app`: Servicio encargado del trámite de retiros, migrado para despachar peticiones a través del Gateway con fallback legacy.
- `gateway`: Capa de transición central que expone la API REST canónica, gestiona autenticación RBAC, audita eventos y encapsula el esquema.
- `tests`: Contenedor bajo el profile test encargado de ejecutar las pruebas automatizadas y publicar reportes JUnit XML.

## Uso

El API Gateway expone las siguientes rutas canónicas protegidas en el puerto 8082:

- `GET /health`: Diagnóstico de disponibilidad del gateway y verificación de conectividad con la base legacy.
- `GET /api/v1/members/{document}`: Consulta de información unificada del afiliado y su empresa asociada.
- `GET /api/v1/members/{document}/beneficiaries`: Consulta de los beneficiarios vinculados al afiliado titular.
- `GET /api/v1/companies/{id}`: Consulta de datos de la empresa y cálculo de afiliados activos.
- `POST /api/v1/members/{document}/retirements`: Registro transaccional de retiro con control estricto de idempotencia por requestId.
- `GET /api/v1/migration/status`: Reporte del estado de avance de la migración para cada dominio.

## Pruebas

La suite de pruebas automatizadas valida la serialización canónica, la restricción de privilegios de escritura en la app móvil, el enmascaramiento de datos personales en logs y la consistencia de respuestas de error. Se ejecutan mediante el comando:

```bash
docker compose --profile test run --rm tests
```

## Documentación

Consulte los documentos complementarios del diseño técnico y especificaciones:

- Arquitectura de la solución: [docs/architecture.md](docs/architecture.md)
- Matriz de lectura y escritura del legacy: [docs/dependency-map.md](docs/dependency-map.md)
- Estrategia por dominios y rollback: [docs/migration-plan.md](docs/migration-plan.md)
- Especificación de interfaces OpenAPI 3.0: [openapi.yaml](openapi.yaml)
- Bitácora de asistencia de inteligencia artificial: [AI_USAGE.md](AI_USAGE.md)

## Qué resolvimos

Desacoplamos con éxito el dominio crítico de Afiliaciones de la base de datos heredada aplicando el patrón Strangler Fig. El portal y la aplicación móvil ahora operan sobre un modelo canónico estandarizado sin acoplamiento a las tablas legacy; los retiros tramitados desde subsidios se asientan de forma idempotente tanto en el esquema moderno como en el histórico; el adaptador absorbe de forma transparente los cambios de esquema del DBA en caliente y el procedimiento de rollback devuelve el dominio al estado inicial sin interrupciones.

## Limitaciones y pendientes

La capa de transición cubre actualmente el dominio de Afiliaciones en modo DUAL. Queda como trabajo futuro extender este mismo patrón hacia los dominios de Aportes y Liquidación de Subsidios, así como reemplazar las consultas SQL directas de la aplicación de Educación una vez se defina el contrato de servicios correspondiente.
