# Cloud Run Social MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ejecutar `social-mcps` tanto en local como remotamente mediante HTTPS, manteniendo el transporte `stdio` local, desplegando `unified-mcp` en Google Cloud Run y pasando el acceso remoto por un gateway de Cloudflare sin depender todavía de un dominio comprado.

**Architecture:** `unified-mcp` conservará dos modos de ejecución: `stdio` para clientes MCP locales y `streamable-http` para Cloud Run. Cloud Run ejecutará el servidor Python completo dentro de un contenedor y conservará las herramientas compatibles con APIs HTTP; `social-automation-mcp`, que depende de Chromium/Playwright y sesiones locales, seguirá siendo exclusivamente local. Un Cloudflare Worker llamado `social-mcps` hará de gateway HTTPS usando la URL `workers.dev`, validará el token del cliente y reenviará las peticiones al servicio de Cloud Run con su propio secreto de upstream. Cuando exista un dominio, el Worker podrá recibir un dominio personalizado sin cambiar el endpoint MCP.

**Tech Stack:** Python 3, FastMCP, `stdio`, Streamable HTTP, Uvicorn, Docker, Google Cloud Run, Artifact Registry, Cloudflare Workers, Wrangler, TypeScript, Git.

## Global Constraints

- El servidor debe seguir funcionando localmente por `stdio` con el comando/configuración actual.
- El endpoint remoto debe usar HTTPS y MCP Streamable HTTP en `/mcp`.
- `social-automation-mcp` no se desplegará en Cloud Run ni Cloudflare: Playwright, Chromium y sus sesiones permanecen en local.
- Las credenciales de redes sociales, WordPress, Gemini y MCP nunca se escribirán en Git, imágenes Docker, URLs ni logs.
- El acceso remoto debe exigir autenticación; no se aceptará un endpoint MCP público sin token.
- Las operaciones de publicación y borrado conservarán sus controles actuales, incluido `dry_run` cuando exista.
- Los nombres visibles de recursos deben usar `social-mcps`, `social_mcps` o `SocialMcps`.
- Los identificadores que impongan minúsculas, guiones o unicidad global usarán `social-mcps` más un sufijo técnico solo cuando la plataforma lo exija.
- Google Cloud se ubicará inicialmente en `europe-southwest1` si la cuenta y el servicio lo permiten; se usará una región europea alternativa solo si esa región no está disponible.
- Mientras no haya dominio propio, el endpoint público de Cloudflare será el nombre `workers.dev` generado por la cuenta; no se inventará un dominio personalizado.
- No se renombrará `master` a `main` ni se alterará la rama base sin una instrucción explícita adicional.
- La rama de implementación será `codex/cloud-run-social-mcp`.

---

## Estado actual y límites conocidos

- La rama base local es `master`, está enlazada con `origin/master` y fue actualizada mediante fast-forward antes de crear esta rama.
- `unified-mcp/server.py` ya selecciona `stdio` por defecto y `streamable-http` cuando `MCP_TRANSPORT` no es `stdio`.
- `unified-mcp/server.py` ya expone autenticación Bearer mediante `MCP_AUTH_TOKEN` para el modo HTTP.
- `unified-mcp/requirements.txt` ya incluye FastMCP, Uvicorn, clientes HTTP y los SDK necesarios para las plataformas API.
- `render.yaml` documenta una configuración remota previa, pero no será la fuente de verdad del despliegue en Google Cloud.
- `social-automation-mcp/src/index.ts` usa `StdioServerTransport` y no forma parte del servicio remoto.
- No se ha asumido que exista un proyecto de Google Cloud ni un Worker de Cloudflare con el nombre solicitado; ambos deben comprobarse con las cuentas autenticadas.

---

### Task 1: Confirmar cuentas, proyectos y nombres de despliegue

**Files:**
- Create: `docs/deployment/social-mcps-cloud-inventory.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: identidad autenticada de `gcloud`, cuenta activa de Wrangler y estado actual del repositorio.
- Produces: inventario reproducible de proyecto Google Cloud, cuenta/subdominio Cloudflare, región, nombres y URLs provisionales.

- [ ] **Step 1: Comprobar identidades sin mostrar secretos**

  Ejecutar comprobaciones de identidad y conservar solo proveedor, cuenta anonimizada, proyecto activo, organización y estado de autenticación. No copiar tokens ni valores de credenciales a ningún archivo.

- [ ] **Step 2: Enumerar proyectos Google Cloud accesibles**

  Buscar un proyecto cuyo nombre visible o identificador contenga `social-mcps`, `social_mcps` o `SocialMcps`. Si no existe y la cuenta tiene permiso para crear proyectos, crear un proyecto con nombre visible `social-mcps` y un ID técnico globalmente único derivado de `social-mcps`.

- [ ] **Step 3: Comprobar facturación y APIs necesarias**

  Confirmar antes de desplegar que el proyecto tiene una cuenta de facturación válida y habilitar únicamente las APIs necesarias: Cloud Run, Artifact Registry, Cloud Build y Resource Manager. Si falta facturación o permisos de creación, detenerse y pedir autorización/instrucciones.

- [ ] **Step 4: Comprobar el espacio de nombres Cloudflare**

  Verificar la cuenta activa de Wrangler y si el nombre `social-mcps` está libre dentro de esa cuenta. Si está libre, reservarlo para el Worker gateway; si ya existe, usar `social_mcps` o `SocialMcps` según lo que acepte Wrangler.

- [ ] **Step 5: Guardar el inventario sin secretos**

  Documentar únicamente IDs, nombres, región, URLs públicas, nombres de servicio y comandos de referencia en `docs/deployment/social-mcps-cloud-inventory.md`. Añadir el inventario al README solo si aporta instrucciones reutilizables y no contiene datos personales sensibles.

- [ ] **Step 6: Ejecutar la comprobación**

  Revisar el inventario con una búsqueda de patrones sensibles (`TOKEN`, `SECRET`, `PASSWORD`, claves privadas y valores Bearer) y confirmar que solo contiene nombres e identificadores no secretos.

### Task 2: Separar la configuración local y remota sin romper `stdio`

**Files:**
- Modify: `unified-mcp/server.py`
- Modify: `unified-mcp/.env.example`
- Create: `unified-mcp/tests/test_server_transport.py`

**Interfaces:**
- Consumes: `MCP_TRANSPORT`, `MCP_AUTH_TOKEN` y `PORT`.
- Produces: arranque local determinista por `stdio`, arranque HTTP determinista para Cloud Run y middleware Bearer testeable.

- [ ] **Step 1: Escribir pruebas de selección de transporte**

  Cubrir explícitamente estos casos: ausencia de `MCP_TRANSPORT` selecciona `stdio`; `MCP_TRANSPORT=stdio` no crea un listener HTTP; `MCP_TRANSPORT=streamable-http` crea la aplicación HTTP; `PORT` se convierte a entero; y una petición HTTP sin Bearer válido recibe `401`.

- [ ] **Step 2: Ejecutar las pruebas nuevas y confirmar que fallan o detectan huecos**

  Ejecutar `python -m unittest discover -s unified-mcp/tests -p "test_*.py" -v`. Si el proyecto usa pytest en el entorno activo, ejecutar también `pytest unified-mcp/tests/test_server_transport.py -q`. Registrar el fallo concreto antes de tocar la implementación.

- [ ] **Step 3: Extraer la configuración de ejecución a una unidad testeable**

  Mantener el comportamiento público de `server.py`, pero aislar la lectura y validación de `MCP_TRANSPORT`, `MCP_AUTH_TOKEN` y `PORT` para que las pruebas no tengan que arrancar un proceso permanente ni publicar credenciales.

- [ ] **Step 4: Mantener el contrato HTTP del endpoint**

  Conservar `/mcp`, `streamable-http`, `0.0.0.0` y el Bearer upstream. No aceptar una configuración remota sin `MCP_AUTH_TOKEN`; el arranque debe fallar de forma explícita o dejar una señal de error clara, según el contrato actual que cubran las pruebas.

- [ ] **Step 5: Documentar variables**

  Actualizar `.env.example` con bloques separados para local y Cloud Run: `MCP_TRANSPORT=stdio` local; `MCP_TRANSPORT=streamable-http`, `PORT=8080` y `MCP_AUTH_TOKEN` remoto.

- [ ] **Step 6: Ejecutar la batería existente y la nueva**

  Ejecutar todas las pruebas del directorio `unified-mcp/tests` y comprobar que el modo local no abre puertos ni emite datos sensibles en stdout.

### Task 3: Crear el contenedor reproducible para Cloud Run

**Files:**
- Create: `unified-mcp/Dockerfile`
- Create: `unified-mcp/.dockerignore`
- Create: `deploy/google-cloud/cloudrun.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: `unified-mcp/requirements.txt`, `server.py`, variables de entorno y el puerto `8080`.
- Produces: imagen ejecutable con `python server.py`, listener HTTP en `$PORT` y sin archivos de secretos incluidos.

- [ ] **Step 1: Escribir la prueba de construcción y arranque**

  Definir una comprobación de integración que construya la imagen, arranque un contenedor con `MCP_TRANSPORT=streamable-http`, `MCP_AUTH_TOKEN=test-only-token` y `PORT=8080`, verifique que el proceso escucha, reciba `401` sin token y no registre el token.

- [ ] **Step 2: Crear el Dockerfile mínimo**

  Usar una imagen Python estable y ligera, instalar únicamente `requirements.txt`, copiar el código de `unified-mcp`, definir `PORT=8080`, configurar `MCP_TRANSPORT=streamable-http` y arrancar con `python server.py`. No copiar `.env`, sesiones Playwright, cachés ni artefactos compilados.

- [ ] **Step 3: Crear `.dockerignore`**

  Excluir `.env*`, `__pycache__`, `.pytest_cache`, `.git`, tests locales sensibles, archivos de sesión, `auth/`, logs y cualquier clave o token.

- [ ] **Step 4: Documentar las variables Cloud Run**

  Crear `deploy/google-cloud/cloudrun.env.example` con nombres de variables, descripción, origen esperado y si es secreto. No incluir valores de ejemplo que parezcan credenciales reales.

- [ ] **Step 5: Construir y arrancar localmente la imagen**

  Ejecutar la comprobación del contenedor con un token ficticio, probar `/mcp` con y sin Bearer y detener el contenedor al terminar.

- [ ] **Step 6: Verificar que el contenido de la imagen no contiene secretos**

  Inspeccionar el contexto de build y las variables de la imagen sin imprimir el contenido de ningún `.env` ni secreto.

### Task 4: Desplegar `unified-mcp` en Google Cloud Run

**Files:**
- Create: `deploy/google-cloud/deploy.ps1`
- Create: `deploy/google-cloud/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: proyecto Google Cloud confirmado en Task 1, repositorio Artifact Registry `social-mcps`, imagen `social-mcps/unified-mcp` y secretos de plataforma introducidos mediante Secret Manager o variables protegidas.
- Produces: servicio Cloud Run `social-mcps`, URL HTTPS provisional y endpoint upstream `/mcp` autenticado.

- [ ] **Step 1: Crear el repositorio de imágenes**

  Crear un repositorio Artifact Registry llamado `social-mcps` en la región elegida y habilitar autenticación para Cloud Build/Cloud Run sin guardar credenciales Docker en el repositorio.

- [ ] **Step 2: Crear los secretos del servidor**

  Guardar `MCP_AUTH_TOKEN` y las credenciales de plataformas como secretos gestionados. No usar `.env` local para cargar secretos en producción ni pasarlos en la línea de comandos si quedan registrados en el historial.

- [ ] **Step 3: Construir y publicar la imagen**

  Etiquetar la imagen con el proyecto y repositorio `social-mcps`, usar una etiqueta inmutable basada en el commit y publicar la imagen en Artifact Registry.

- [ ] **Step 4: Crear el servicio Cloud Run**

  Desplegar el servicio con nombre `social-mcps`, `MCP_TRANSPORT=streamable-http`, puerto `8080`, mínimo de instancias `0`, máximo conservador de instancias y autenticación de aplicación mediante `MCP_AUTH_TOKEN`. Permitir entrada pública solo porque el Worker gateway será la capa de acceso, y exigir el Bearer upstream dentro de la aplicación.

- [ ] **Step 5: Probar el endpoint directo**

  Obtener la URL HTTPS de Cloud Run y probar `/mcp` con el MCP Inspector o un cliente compatible: sin token debe devolver `401`; con token debe completar la negociación MCP; una herramienta de lectura y una operación `dry_run` deben responder correctamente.

- [ ] **Step 6: Documentar rollback y costes**

  Documentar cómo volver a una revisión anterior, cómo revisar logs y cómo limitar instancias/recursos. Añadir una advertencia clara de que cuotas gratuitas no equivalen a coste ilimitado y que logs, tráfico o servicios auxiliares pueden facturarse.

### Task 5: Crear el gateway Cloudflare `social-mcps`

**Files:**
- Create: `cloudflare-mcp-gateway/package.json`
- Create: `cloudflare-mcp-gateway/tsconfig.json`
- Create: `cloudflare-mcp-gateway/wrangler.jsonc`
- Create: `cloudflare-mcp-gateway/src/index.ts`
- Create: `cloudflare-mcp-gateway/test/gateway.test.ts`
- Create: `cloudflare-mcp-gateway/README.md`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: `UPSTREAM_MCP_URL`, secreto `UPSTREAM_MCP_AUTH_TOKEN` y token de cliente `MCP_CLIENT_TOKEN`.
- Produces: `https://social-mcps.<subdominio>.workers.dev/mcp`, proxy de métodos/headers/body hacia Cloud Run, autenticación de cliente y respuestas streaming sin almacenar credenciales.

- [ ] **Step 1: Escribir pruebas del proxy**

  Cubrir: ruta `/mcp` permitida; rutas ajenas rechazadas; método HTTP conservado; cuerpo conservado; token de cliente ausente o incorrecto responde `401`; token de cliente correcto añade el Bearer upstream sin devolverlo; y la respuesta del upstream se retransmite sin leerla completa en memoria.

- [ ] **Step 2: Crear el Worker mínimo**

  Implementar `src/index.ts` como proxy estrecho: validar el token del cliente, construir la URL upstream, copiar solo headers permitidos, inyectar `Authorization` del secreto y devolver el `Response` del upstream. No registrar bodies, tokens ni cabeceras de autorización.

- [ ] **Step 3: Configurar Wrangler**

  Usar el nombre `social-mcps`, declarar `UPSTREAM_MCP_URL` como variable no secreta y reservar `UPSTREAM_MCP_AUTH_TOKEN` y `MCP_CLIENT_TOKEN` para secretos de Wrangler. No usar dominio personalizado todavía.

- [ ] **Step 4: Probar en local**

  Ejecutar el Worker con un upstream local o el endpoint de Cloud Run, probar negociación MCP, `401`, `dry_run`, streaming y propagación de errores. El test no usará tokens reales.

- [ ] **Step 5: Desplegar en Cloudflare**

  Crear o reutilizar el Worker `social-mcps` solo después de confirmar la cuenta y el nombre. Publicar en `workers.dev`, configurar secretos mediante Wrangler y registrar la URL pública provisional.

- [ ] **Step 6: Probar extremo a extremo**

  Conectar un cliente MCP a `https://social-mcps.<subdominio>.workers.dev/mcp`, verificar herramientas visibles, ejecutar lectura y `dry_run`, y confirmar que el endpoint directo de Cloud Run no se usa desde el cliente final.

### Task 6: Conservar el doble modo local/remoto y la separación Playwright

**Files:**
- Modify: `README.md`
- Modify: `social-automation-mcp/README.md`
- Create: `docs/deployment/social-mcps-runtime-matrix.md`

**Interfaces:**
- Consumes: URLs y nombres confirmados en Tasks 1, 4 y 5.
- Produces: configuración local, configuración remota y matriz clara de qué herramientas viven en cada entorno.

- [ ] **Step 1: Documentar el perfil local**

  Mantener `unified-mcp` por `stdio` y `social-automation-mcp` por `stdio`/Playwright con rutas Windows válidas, sin exigir red ni dominio.

- [ ] **Step 2: Documentar el perfil remoto**

  Añadir el endpoint Cloudflare `/mcp`, el header del token de cliente y la advertencia de que las herramientas basadas en Playwright no aparecen en el servicio remoto.

- [ ] **Step 3: Crear la matriz de herramientas**

  Listar LinkedIn, Instagram, Facebook Page, Threads, WordPress, X/Twikit e imagen como remotas si pasan sus pruebas; listar X/Playwright y Facebook feed personal como locales.

- [ ] **Step 4: Validar la documentación contra el código**

  Comparar nombres de herramientas, variables y endpoints con `server.py`, `social-automation-mcp/src/index.ts` y los README existentes. Corregir cualquier discrepancia antes de cerrar el plan de implementación.

### Task 7: Seguridad, observabilidad y entrega

**Files:**
- Create: `docs/deployment/social-mcps-security.md`
- Create: `docs/deployment/social-mcps-operations.md`
- Modify: `README.md`
- Test: `unified-mcp/tests/test_server_transport.py`
- Test: `cloudflare-mcp-gateway/test/gateway.test.ts`

**Interfaces:**
- Consumes: despliegues operativos de Cloud Run y Cloudflare.
- Produces: checklist de seguridad, diagnóstico, rollback y criterios de aceptación.

- [ ] **Step 1: Definir observabilidad mínima**

  Documentar logs estructurados sin secretos, revisión de errores 401/5xx, identificación de revisión Cloud Run y comprobación de despliegues Cloudflare.

- [ ] **Step 2: Definir límites y rollback**

  Documentar máximo de instancias, revisión estable anterior, despliegue gradual si está disponible y eliminación segura de revisiones o imágenes antiguas solo tras confirmar que no se necesitan.

- [ ] **Step 3: Ejecutar pruebas de seguridad**

  Confirmar que no aparecen tokens en logs, imágenes, respuestas de error, URLs, commits ni artefactos de test; confirmar que el gateway no puede convertirse en un proxy abierto cambiando arbitrariamente la URL upstream.

- [ ] **Step 4: Ejecutar aceptación funcional**

  Verificar todos estos casos: local `stdio`; Cloud Run directo protegido; Cloudflare `/mcp` protegido; herramienta de lectura; herramienta `dry_run`; error de API externa; reinicio del contenedor; y fallback local de Playwright.

- [ ] **Step 5: Actualizar README y hacer commit por unidad**

  Ejecutar las pruebas finales, revisar el diff, documentar el resultado y crear commits pequeños con mensajes descriptivos. No publicar ni fusionar la rama sin revisión explícita.

---

## Criterios de aceptación

- `unified-mcp` continúa arrancando por `stdio` en local.
- Cloud Run sirve el mismo MCP mediante HTTPS y `/mcp` sin depender del PC.
- Cloudflare expone un endpoint `workers.dev` llamado `social-mcps` y retransmite MCP sin convertirse en proxy abierto.
- El cliente remoto usa Cloudflare, no la URL directa de Cloud Run.
- Las credenciales permanecen fuera de Git, Docker, logs y respuestas.
- Las herramientas Playwright continúan disponibles en local y no se anuncian falsamente como remotas.
- Se puede ejecutar una operación de lectura y una operación `dry_run` de extremo a extremo.
- El despliegue tiene instrucciones de diagnóstico y rollback.
- Ningún dominio personalizado es necesario para la primera versión.

## Preguntas que bloquean el despliegue, si aparecen durante el preflight

1. Si la cuenta Google Cloud no tiene facturación activa o permisos para crear proyecto, se detendrá el despliegue y se pedirá la decisión del proyecto/cuenta a utilizar.
2. Si la cuenta Cloudflare no permite crear el Worker o el nombre `social-mcps` está ocupado, se detendrá antes de elegir un nombre distinto automáticamente.
3. Si una API social exige una URL de callback con dominio propio, se documentará esa limitación y se pedirá decidir si se usa temporalmente la URL `workers.dev` o se espera a comprar el dominio.
4. Si las pruebas muestran que alguna plataforma no tolera el entorno Cloud Run o el proxy streaming, se mantendrá esa plataforma en local y se consultará antes de cambiar la arquitectura.

## Verificación del plan

- Cobertura: local `stdio`, remoto HTTPS, Google Cloud Run, Cloudflare gateway, nombres de recursos, ausencia de dominio, autenticación, secretos, Playwright local, pruebas, observabilidad y rollback.
- Sin marcadores pendientes: no se dejan instrucciones sin comando, archivo o resultado esperado.
- Consistencia: todos los recursos principales usan `social-mcps`; los identificadores con restricciones pueden añadir un sufijo técnico documentado.
- Alcance: esta rama contiene inicialmente la planificación y el preflight; la implementación se ejecutará por tareas con revisión entre bloques.
