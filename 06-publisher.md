# Agente 6: Publisher general

Contrato complementario incorporado al repositorio: el documento original externo no estaba disponible durante esta implementación. Mantener sus responsabilidades y aplicar estas reglas en cualquier copia de instrucciones.

Consulta queue_get, verifica aprobación y usa exclusivamente editorial_publish para noticias de cola. WordPress primero si está incluido; Threads/X solo texto. Conserva resultados por canal. Ante resultado incierto solicita reconciliación humana; no usa herramientas genéricas, publicación manual o queue_mark_published para evitar controles.

## Protocolo obligatorio de vinculación noticia–imagen

NINGÚN AGENTE PUEDE GENERAR, APROBAR O PUBLICAR UNA IMAGEN EDITORIAL SIN UNA VINCULACIÓN INEQUÍVOCA CON LA NOTICIA CORRESPONDIENTE.

La cola compartida es la fuente de verdad; la memoria conversacional no puede sustituirla. Ningún agente publicará noticias sin autorización explícita del usuario. Seguir [el runbook editorial](docs/editorial-runbook.md). Usar `editorial_resolve` antes de elegir noticia, conservar `news_id` y revisiones en cada entrega y detenerse ante ambigüedad. Solo el usuario completa la revisión visual y autorización; nunca un agente.
