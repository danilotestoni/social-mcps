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
   almacena bytes inmutables. Admite HTTPS OpenAI/ChatGPT/WordPress y enlaces
   temporales firmados del propio servicio; URLs
   inaccesibles, HTML sin imagen y redirecciones ajenas se rechazan.
   Para Claude/Codex sin generador nativo: `generate_image(prompt=visual_prompt,
   news_id, generation_id, upload_to_wordpress=false)` genera y vincula en servidor.
   Si el usuario aporta una imagen adjunta, usa `upload_chat_image(file=...)`:
   el host ChatGPT entrega el objeto de archivo con `download_url` y `file_id`
   mediante `openai/fileParams`. No inventes ese objeto ni uses rutas `/mnt/data`,
   referencias `sandbox:` o IDs como `image_url`. La herramienta valida y conserva
   los bytes originales, devuelve URL temporal y SHA-256 y no modifica la noticia.
   Vincula después su `public_url` con `editorial_bind_image` a la generación
   preparada. No regeneres ni sustituyas una imagen aportada por el usuario.
   Si el catálogo aún no muestra `upload_chat_image`, actualiza las herramientas
   del complemento y repite; no des por probada una transferencia no ejecutada.
   No se debe llamar a `upload_temp_image` como sustituto de la vinculación.
5. `editorial_request_review(news_id)` devuelve un enlace de 30 minutos a una página
   adaptada a móvil (también usable en web/app, modo claro y oscuro). El **usuario**
   ve la imagen y el texto de cada canal, desmarca los canales que no quiera y pulsa
   **«Aprobar y publicar»**: ese único botón confirma la correspondencia visual y
   autoriza los canales marcados. Nombre y nota son opcionales. Si no ve la imagen o
   corresponde a otra noticia, no aprueba. Los agentes no envían ese formulario y la
   aprobación no se crea desde parámetros MCP. Tras guardar, vuelve al chat y escribe
   «publica»; el formulario no invoca plataformas sociales.
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
gana una reserva. Una respuesta positiva de una API sin ID externo es incierta. Los resultados
confirmados guardan ID, URL cuando la API la proporciona, fecha y respuesta.
Una API que confirma ID pero no devuelve permalink conserva `url=null`; no se
inventa una URL. WordPress requiere además estado `publish`.

No existe transacción distribuida GCS/red social. Si el proceso muere tras publicar
y antes de guardar, queda reservado. Si hay timeout/error, queda incierto. No hay
caducidad que habilite un reintento automático. Tampoco se reintenta automáticamente
una publicación fallida: incluso un rechazo necesita reconciliación conservadora.
Los clientes de publicación solo reintentan errores de conexión previos al envío;
las lecturas/polling y preparación de contenedores conservan su comportamiento.

Para resolver hay dos vías equivalentes, ambas multicanal:

- `editorial_reconcile(news_id, results, actor)` desde el chat, cuando el usuario
  indica el resultado o un agente lo verificó con herramientas de lectura de la
  plataforma. `results` es una lista: `{"channel", "outcome": "published"|"published_manual"|"absent",
  "url"?, "external_id"?, "evidence"?}`. No requiere formulario.
- La sección «Conciliar canales» de la página de revisión, que permite marcar
  varios canales en un solo envío.

Reglas comunes:

- Publicado: basta la URL https; el ID se deduce de ella cuando es posible (X,
  Threads, LinkedIn). Sirve también para canales publicados fuera del servidor
  (por ejemplo X desde el equipo local), aunque no haya intento previo.
- Publicación manual confirmada por el usuario: `outcome="published_manual"`,
  `confirmed_by` (nombre de la persona) y `evidence` (su confirmación expresa)
  son obligatorios. URL e ID externo son opcionales; sin ellos se guardan como
  `null`, nunca se inventan. Solo se aplica a los canales indicados y preparados.
  El canal guarda `publication_method="manual"`, `verification="user_confirmation"`,
  persona que confirma, agente que registra, fecha y evidencia. El recibo conserva
  el intento anterior, si existía. Esta confirmación no equivale a verificación
  directa en la plataforma y no ejecuta ninguna publicación.
  No usar esta opción por una suposición del agente ni por un timeout.
  Ejemplo desde el chat:
  ```json
  {"news_id":"2026-10-19-noticia-3","actor":"codex","results":[
    {"channel":"threads","outcome":"published_manual","confirmed_by":"Danilo",
     "evidence":"El usuario confirma expresamente que publicó esta noticia a mano en Threads."}
  ]}
  ```
  En el formulario, seleccionar «Lo publiqué manualmente» e indicar nombre y
  confirmación; el enlace es opcional. Los canales cerrados se muestran como
  «Publicado manualmente» y no se vuelven a seleccionar para publicar.
- No publicado: libera el intento incierto, conserva el recibo y permite un nuevo
  intento explícito. Un timeout por sí solo no demuestra ausencia.
- Cuando todos los canales aprobados quedan confirmados, la noticia pasa a
  `publicada` automáticamente.

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


## Android: subida directa por fragmentos

Pedir `open_chunked_image_upload` para abrir el selector dentro del chat.
Elegir de nuevo la imagen del móvil en ese componente y pulsar **Subir por fragmentos**.
El selector necesita una elección explícita; no puede leer por su cuenta un adjunto anterior.
JavaScript llama al inicio, envía partes de 32768 bytes y finaliza con `expected_sha256`
y `auto_optimize=false`. El servidor rechaza una reconstrucción distinta antes de almacenar
el objeto final; el componente compara el hash y el tamaño devueltos y muestra el enlace HTTPS.
Un corte conserva el identificador y el último fragmento confirmado mientras el componente
siga abierto: **Reintentar subida** reenvía desde ese punto. No publica ni modifica noticias.
Al desplegar, actualizar herramientas de la conexión y abrir un chat nuevo.
Las pruebas locales del componente no sustituyen la prueba en el cliente Android real.
