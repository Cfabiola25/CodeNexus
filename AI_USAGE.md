# Uso de inteligencia artificial

<!--
Plantilla con el formato obligatorio. Registren al menos 3 usos relevantes (agreguen "## Uso 4", etc. si hay más).
- Los cinco campos deben estar llenos.
- "Qué modificó o corrigió el equipo" debe explicar la corrección en 8 palabras o más.
- Si no hay ningún uso completo, se aplica la penalización de −5 puntos.
Revisen con: ./validator entregables
-->

## Uso 1
- Herramienta: ChatGPT
- Para qué se usó: Diagnóstico de resolución de red y conectividad entre Subsidios y el API Gateway en Docker Compose
- Prompt principal (resumido): "¿Cómo configurar la URL de conexión entre contenedores en docker compose para que subsidios llame al gateway por HTTP?"
- Qué produjo: Sugirió configurar la variable GATEWAY_URL apuntando a http://localhost:8082 dentro del contenedor.
- Qué modificó o corrigió el equipo: Descartamos localhost porque entre contenedores de Docker no resuelve al host; en su lugar configuramos el nombre del servicio de la red interna http://gateway:8082 con fallback automático.

## Uso 2
- Herramienta: Claude
- Para qué se usó: Diseño de la expresión regular para enmascarar números de documento en las rutas de auditoría
- Prompt principal (resumido): "Regex para reemplazar cédulas de más de 4 dígitos en rutas de URL dejando visibles solo los últimos cuatro"
- Qué produjo: Una función con re.sub que reemplazaba todos los números por asteriscos fijos de 4 caracteres.
- Qué modificó o corrigió el equipo: La solución de la IA alteraba la longitud real del documento; la corregimos para conservar el tamaño original usando asteriscos dinámicos y preservando exactamente los últimos cuatro dígitos.

## Uso 3
- Herramienta: Gemini
- Para qué se usó: Estructuración del manejo dinámico de excepciones de PostgreSQL ante el cambio de esquema del DBA
- Prompt principal (resumido): "Cómo capturar en Python psycopg2 cuando una tabla o columna fue renombrada para hacer fallback a otra consulta"
- Qué produjo: Propuso un bloque try-except Exception genérico que capturaba cualquier error de base de datos.
- Qué modificó o corrigió el equipo: Un bloque genérico ocultaba caídas de conexión o sintaxis; restringimos la captura exclusivamente a psycopg2.errors.UndefinedTable y UndefinedColumn para conmutar entre esquemas de forma segura.
