# Protocolo noticia–imagen: diseño y plan de implementación

Objetivo autorizado: implementar, probar, integrar y desplegar sin publicar noticias reales.

## Diseño

La cola GCS sigue siendo la fuente de verdad. Cada noticia conserva contenido y
metadatos históricos y añade un sobre editorial versionado. Todas las transiciones
usan la generación leída, incluida la lectura de bytes, y CAS de GCS. El contenido
y los payloads exactos de publicación se firman mediante SHA-256. Cada nueva
generación visual obtiene un identificador aleatorio ligado al ID/revisión.

Una imagen descargada se decodifica, se almacena inmutable en el bucket de la cola
y se identifica por su hash real. La URL de origen es procedencia, nunca aprobación.
Una página de revisión humana muestra noticia, imagen y payloads: exige descripción
visual, correspondencia editorial y autorización expresa por canales. Las herramientas
MCP no pueden escribir directamente aprobaciones. La página usa un enlace temporal
de capacidad; no acredita identidad civil ni protege frente a un cliente malicioso
con acceso al enlace. Sí separa la aprobación del flujo automático normal.

La publicación protegida solo recibe ID, revisiones y canal; usa exclusivamente
payloads/activo/aprobación persistentes. Reserva el intento mediante CAS antes de
cualquier API social. No caducan automáticamente reservas inciertas. El resultado
se combina por canal y se conserva para reconciliación humana sin volver a publicar.
Los cambios se bloquean mientras un intento esté reservado o incierto.

Las herramientas genéricas mantienen su función para trabajo ajeno a la cola,
con declaración explícita de ese uso en despliegues que tengan cola.
No existe un clasificador infalible que pueda detectar todo texto parafraseado
como perteneciente a una cola; esta frontera se documenta, no se promete eliminarla.

## Plan (ejecución en esta sesión)

- [ ] Pruebas de transiciones, revisiones, rechazos semánticos y compatibilidad.
- [ ] Sobre editorial, lectura consistente y CAS; activos inmutables.
- [ ] Resolución, preparación, vinculación, revisión humana y publicación protegida.
- [ ] Pruebas de concurrencia realista, resultado incierto, reconciliación y rutas.
- [ ] Instrucciones coherentes de agentes, diaria/semanal y runbook/rollback.
- [ ] Suite completa, análisis estático, revisión de diff y secretos; PR y CI.
- [ ] Merge y despliegue conservando configuración; verificación MCP por gateway.

## Puntos de revisión

Lectura/escritura GCS concurrente; aprobación de revisión obsoleta; hash igual en
noticia distinta; reserva abandonada tras API; datos históricos sin aprobación.
La verificación visual humana debe rechazar NVIDIA/Claude, Moonshot/Gemini y
Kolibri reutilizado. No basta una etiqueta o un MIME. Las pruebas simulan esa
decisión humana; no afirman medir un clasificador visual que no existe.

## Evidencia inicial

Master remoto/local b17dd84. Producción socialmcps/europe-west1/unified-mcp,
revisión unified-mcp-00023-l4t con 100% del tráfico. Documentos 01–06 y diaria/
semanal no localizados en este repositorio; se incorporarán contratos complementarios
sin inventar haber actualizado originales externos.
