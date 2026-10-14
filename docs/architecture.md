# Arquitectura

Documento de arquitectura de software para la capa de transición del dominio Afiliaciones en la Caja de Compensación Familiar.

## Contexto

La Caja de Compensación Familiar opera históricamente sobre una base de datos relacional heredada (PostgreSQL emulando el modelo Informix) que se convirtió en el punto único de acoplamiento para múltiples aplicaciones críticas como Educación, Subsidios, Portal de Servicios y reportes regulatorios. El problema fundamental radica en que cualquier alteración en el esquema de la base de datos (renombrar columnas o tablas) genera roturas en cadena sobre los consumidores. La dirección técnica estableció la directriz de modernizar sin apagar el negocio mediante la implementación del patrón Strangler Fig (estrangulación progresiva), prohibiendo que cualquier servicio nuevo se conecte directamente a la base legacy e introduciendo una capa intermedia de transición desacoplada y tolerante a fallos.

## Componentes

La arquitectura de la solución se fundamenta en los siguientes componentes modulares:

1. **API Gateway (`gateway:8082`):** Expone la interfaz REST canónica hacia los consumidores autorizados (Portal, Subsidios y App Móvil). Implementa el middleware de seguridad por tokens Bearer, control de permisos RBAC, despacho de eventos a auditoría estructurada en `logs/audit.log` y manejo de resiliencia con circuit breaker ante caídas de la base de datos.
2. **Modelo Canónico:** Define las estructuras de datos neutrales del dominio (`Member`, `Company`, `Beneficiary`, `Retirement`), aislando por completo las nomenclaturas y códigos crudos de la base legacy hacia los consumidores externos.
3. **Legacy Adapter (`src/adapter/`):** Componente aislado de persistencia encargado de encapsular la complejidad del motor PostgreSQL legacy. Traduce las peticiones canónicas a sentencias SQL compatibles, gestiona el procedimiento almacenado transaccional y absorbe los cambios de esquema sin alterar los contratos externos.
4. **Consumidores Existentes:** `portal-client` (consume vía HTTP), `subsidios-app` (migrado a invocar el Gateway vía HTTP) y `educacion-app` (mantiene su consulta SQL histórica directa sin verse afectado).

## Modelo canónico

El modelo canónico representa las entidades del negocio en un lenguaje ubicuo y estandarizado, desvinculado de los nombres de columnas o abreviaturas heredadas de sistemas previos:

- **Member:** Modela la información del afiliado consolidando los nombres completos en un único campo canónico `fullName`, su número de documento sin caracteres especiales, el estado de afiliación normalizado a una enumeración (`ACTIVE`, `RETIRED`, `SUSPENDED`) y la referencia estructurada a su empresa empleadora (`id`, `name`).
- **Company:** Representa a la empresa aportante con su identificación única, razón social y el cálculo agregado en tiempo real de sus miembros activos (`activeMembers`).
- **Beneficiary:** Modela los beneficiarios a cargo del trabajador afiliado, incluyendo documento, nombre completo y parentesco estandarizado.
- **Retirement:** Modela la solicitud de retiro mediante un identificador único idempotente (`requestId`), fecha efectiva y justificación del movimiento, evitando duplicidades transaccionales.

## Cambio de esquema

Para soportar el evento de cambio de esquema ejecutado por el DBA (`scripts/schema-change.sh`), donde la tabla `AFI_MAE` se renombra a `PERSON_MASTER` y sus columnas `NRO_DOC` y `EST_AFI` se transforman en `DOCUMENT_NUMBER` y `STATUS_CODE`, la capa de persistencia en el Adapter implementa una estrategia de introspección y consulta adaptativa con fallback. 

El adaptador intenta resolver las consultas contra el esquema canónico moderno (`PERSON_MASTER`); si la tabla aún no existe o la base está en su estado original, captura la excepción de tabla no encontrada y conmuta transparentemente a la consulta sobre la estructura legacy `AFI_MAE`. De este modo, los contratos HTTP y las respuestas hacia Portal, Subsidios y la App Móvil permanecen 100% idénticos y estables antes, durante y después del cambio estructural del DBA.

## Alternativas descartadas

Durante el proceso de diseño se evaluaron y descartaron las siguientes alternativas arquitectónicas:

- **Migración Big Bang de base de datos:** Se descartó realizar una sustitución completa e inmediata de la base de datos legacy hacia un motor nuevo debido al altísimo riesgo operacional para la Caja de Compensación, ya que implicaría suspender la liquidación de subsidios y la matrícula de estudiantes durante una ventana prolongada de mantenimiento no viable para el negocio.
- **Acceso directo mediante Vistas SQL para aplicaciones nuevas:** Se descartó permitir que nuevas aplicaciones móviles y portales consuman directamente vistas o sinónimos en PostgreSQL, debido a que viola la política de seguridad y arquitectura que exige desacoplar las capas de red y aplicar autenticación, auditoría y rate limiting antes de tocar el motor de base de datos.
