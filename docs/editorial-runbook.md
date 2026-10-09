# Runbook del protocolo noticia–imagen

NINGÚN AGENTE PUEDE GENERAR, APROBAR O PUBLICAR UNA IMAGEN EDITORIAL SIN UNA
VINCULACIÓN INEQUÍVOCA CON LA NOTICIA CORRESPONDIENTE.

La cola compartida es la fuente de verdad. La conversación no la sustituye.
Ningún agente publica noticias sin autorización explícita del usuario.

## Flujo para ChatGPT, Claude y Codex

1. `editorial_resolve(fecha_prevista="YYYY-MM-DD")` o `news_id` explícito.
   Usa la fecha local del usuario. Cero o varias noticias, publicada o descartada:
   detenerse y pedir aclaración. No seleccionar por memoria ni por el último tema.
2. Revisa `contenido_markdown`. Prepara payloads completos por canal:
   `{"wordpress":{"title":"...","content":"..."},"facebook":{"text":"..."}}`.
   LinkedIn, Instagram, Threads y X usan también `text`. Si el contenido social
   enlaza al artículo aún no publicado, usa literalmente `[WORDPRESS_URL]`.
   Es la única sustitución posterior permitida, con la URL confirmada del servidor.
3. `editorial_prepare(news_id, expected_version, payloads, actor)` conserva una
   generación pendiente, revisiones, hashes y un `visual_prompt` basado en la cola.
4. Generación nativa de ChatGPT: usa ese prompt, muestra el resultado y solicita
   el enlace compartido de ESA generación. `editorial_bind_image(news_id,
   expected_version, generation_id, source_url, actor)` descarga, decodifica y
   almacena bytes inmutables. Solo admite HTTPS OpenAI/ChatGPT/WordPress; URLs
   inaccesibles, HTML sin imagen y redirecciones ajenas se rechazan.
   Para Claude/Codex sin generador nativo: `generate_image(prompt=visual_prompt,
   news_id, generation_id, upload_to_wordpress=false)` genera y vincula en servidor.
   No se debe llamar a `upload_temp_image` como sustituto de la vinculación.
5. `editorial_request_review(news_id)` devuelve un enlace de 30 minutos. El
   **usuario** abre el enlace e inspecciona imagen/noticia/textos. Todos los canales
   preparados aparecen seleccionados por defecto. Confirma correspondencia
   semántica y autoriza expresamente la publicación. Nombre y comentario son
   opcionales. Si no ve la imagen, reconoce otra marca/noticia o no está seguro,
   no aprueba. Los agentes no envían ese formulario. La aprobación no se crea desde
   parámetros MCP ni metadatos. Tras guardar, vuelve al chat y escribe «publica»;
   el formulario no invoca plataformas sociales.
6. `queue_get` para consultar revisiones y aprobación persistente.
   `editorial_publish(news_id, news_revision, image_revision, channel, actor,
   dry_run=true)` comprueba sin publicar ni reservar.
7. Tras aprobación real, `editorial_publish(..., dry_run=false)`, WordPress primero
   si está en los payloads. El servidor selecciona texto e imagen persistentes;
   el agente no puede cambiarlos en esta llamada. Threads y X mantienen publicación
   solo de texto, pero también exigen la aprobación editorial vigente.
8. Conserva la respuesta y consulta `queue_get`. No llames a `queue_mark_published`:
   la ruta antigua queda bloqueada para registrar publicaciones. Los resultados
   confirmados se combinan por canal, sin sustituir el mapa completo.

## Cambios y revisiones

Modificar contenido incrementa `news_revision` e invalida aprobación. Cambiar la
imagen también invalida aprobación. Preparar otra generación incrementa
`image_revision` y conserva el sobre anterior en `editorial_versions`. Debe volver
a vincularse y revisarse. No cambia los canales ya publicados ni permite duplicarlos.
Durante intentos reservados/inciertos se bloquean edición, preparación y archivo.
Las notas y fechas operativas no cambian el texto aprobado.

La aprobación cubre ID, revisiones, hash del contenido, payloads y activo completo.
Un hash correcto solo identifica bytes: no prueba correspondencia editorial.
La comprobación semántica es **humana**, no un clasificador visual automático.
Las pruebas NVIDIA/Claude y Moonshot/Gemini simulan una revisión humana negativa;
no afirman evaluar reconocimiento de imágenes. El usuario puede equivocarse.

## Idempotencia y reconciliación

Clave por ID/revisión/canal; reserva CAS antes de llamar a la API. Solo un agente
gana una reserva. Una respuesta positiva sin ID externo es incierta. Los resultados
confirmados guardan ID, URL cuando la API la proporciona, fecha y respuesta.
Una API que confirma ID pero no devuelve permalink conserva `url=null`; no se
inventa una URL. WordPress requiere además estado `publish`.

No existe transacción distribuida GCS/red social. Si el proceso muere tras publicar
y antes de guardar, queda reservado. Si hay timeout/error, queda incierto. No hay
caducidad que habilite un reintento automático. Tampoco se reintenta automáticamente
una publicación fallida: incluso un rechazo necesita reconciliación conservadora.
Los clientes de publicación solo reintentan errores de conexión previos al envío;
las lecturas/polling y preparación de contenedores conservan su comportamiento.

Para resolver: consultar la plataforma con herramientas de lectura y abrir
`editorial_request_review`. El usuario selecciona canal y aporta evidencia:

- Publicación existente: confirma manualmente ID y URL. Se conserva resultado.
- Ausencia comprobada: libera ese intento, conserva evidencia y permite un nuevo
  intento explícito. Un timeout por sí solo no demuestra ausencia.

Si GCS falla al guardar después de la API, la respuesta incluye evidencia externa
cuando es posible. No repetir la API; reconciliar con esa evidencia. No marcar un
canal como publicado solo porque se abrió un navegador o una herramienta lo sugirió.

## Compatibilidad y límites

Los objetos históricos se leen sin migración masiva ni aprobaciones inventadas.
Los pendientes pasan por preparar/vincular/revisar. Publicados y descartados no se
reabren automáticamente. Los archivos conservan todo el historial existente.
La propiedad global de un hash impide reutilizar exactamente los mismos bytes para
otra noticia, incluso después de archivar. Una recodificación cambia el hash y debe
ser detectada durante revisión humana. Los activos no se eliminan automáticamente.

Herramientas genéricas: en despliegues con cola, declarar `non_editorial=true`
solo para trabajo ajeno. Contenido exacto o URLs editoriales conocidas se rechazan;
sin cola la API genérica mantiene su comportamiento. El guard no es un clasificador
de texto parafraseado ni una frontera contra un cliente malicioso con credenciales.
Las publicaciones locales/manuales fuera del servidor no se pueden impedir desde
este MCP. El enlace de revisión es una capacidad temporal: no compartirlo con terceros.
El nombre introducido registra responsabilidad, no autentica una identidad personal.
Un agente con acceso al enlace podría abusar de él; la instrucción de no cumplimentarlo
es obligatoria. Autenticación humana independiente requeriría un IdP/credencial aparte.

## Operación y rollback

Producción verificada inicialmente: proyecto `socialmcps`, región `europe-west1`,
servicio `unified-mcp`, revisión anterior `unified-mcp-00023-l4t`, 100% del tráfico.
`PUBLIC_BASE_URL=https://unified-mcp.adasnova.com`; cola `social-mcps-queue`.
No modificar `SOCIAL_MCPS_SECRETS_JSON` ni las referencias existentes de Secret Manager.

Antes del despliegue: suite, estáticos, diff, revisión de secretos, PR y CI.
Desplegar el commit integrado con `gcloud run deploy unified-mcp --source unified-mcp
--project socialmcps --region europe-west1`. Conservar variables, identidad, límites
y referencias de secretos; no pasar un archivo de configuración histórico.

Después: verificar revisión Ready y tráfico; gateway sin token rechazado;
MCP autenticado initialize/tools/list; queue_list/queue_get de solo lectura;
editorial_publish con ID inexistente y con noticia sin aprobación, siempre dry-run.
No publicar noticias reales ni alterar la cola para probar producción.

Rollback ante comprobación crítica fallida:

```powershell
gcloud run services update-traffic unified-mcp --project socialmcps --region europe-west1 --to-revisions unified-mcp-00023-l4t=100
```

Verificar tráfico, conectividad y lectura MCP de nuevo. El rollback de código no
borra datos ni deshace publicaciones. La revisión antigua no impone el protocolo:
pausar el flujo editorial hasta restaurar una revisión protegida. No editar GCS
manualmente para eliminar reservas o aparentar aprobaciones.
