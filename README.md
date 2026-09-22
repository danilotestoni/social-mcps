# social-mcps

Sistema de automatización de redes sociales mediante MCP servers. Está diseñado en dos capas: un **servidor unificado** para despliegue en la nube (Render u otro proveedor) y un **servidor de automatización local** para las acciones que requieren navegador.

---

## Componentes

| Componente | Tipo | Despliegue | Plataformas |
|---|---|---|---|
| `unified-mcp/` | Python FastMCP — API REST | Local o Render | LinkedIn, Instagram, Facebook (Page), Threads, WordPress, X (Twikit) |
| `social-automation-mcp/` | TypeScript FastMCP — Playwright | Solo local | X (Twitter), Facebook feed personal |

### Por qué dos componentes

- La **API oficial de X cuesta $0,20 por post** desde febrero de 2026. Este servidor usa [Twikit](https://github.com/d60/twikit), una librería Python que interactúa con X sin API oficial (~40 MB RAM).
- **Compartir en el feed personal de Facebook** no tiene API REST disponible — solo es posible mediante automatización del navegador (Playwright).
- Playwright requiere Chromium (~826 MB RAM pico), incompatible con el plan gratuito de Render (512 MB). Por eso `social-automation-mcp` es solo local.

---

## Plataformas disponibles

| Plataforma | Servidor | Herramientas MCP |
|---|---|---|
| LinkedIn | `unified-mcp` | `linkedin_publish_post`, `linkedin_get_last_posts`, `linkedin_delete_post`, `linkedin_get_account_info` |
| Instagram | `unified-mcp` | `instagram_publish_post`, `instagram_get_last_posts`, `instagram_delete_post`, `instagram_get_account_info` |
| Facebook (Page) | `unified-mcp` | `facebook_publish_post`, `facebook_get_last_posts`, `facebook_delete_post`, `facebook_get_account_info` |
| Threads | `unified-mcp` | `threads_publish_post`, `threads_get_last_posts`, `threads_delete_post`, `threads_get_account_info` |
| WordPress.com | `unified-mcp` | `wordpress_publish_post`, `wordpress_get_last_posts`, `wordpress_delete_post`, `wordpress_get_account_info` |
| X (Twitter) | `unified-mcp` (Twikit) + `social-automation-mcp` (Playwright) | `x_post_tweet` / `post_to_x` |
| Facebook feed personal | `social-automation-mcp` (Playwright) | `share_to_fb_feed` |
| Generación de imágenes | `unified-mcp` (Gemini + Pollinations.ai) | `generate_image` |

### Generación de imágenes con Gemini + Pollinations.ai (fallback automático)

La tool `generate_image` crea imágenes con **Gemini 3.1 Flash Lite Image** mediante el SDK `google-genai` (API key gratuita en [aistudio.google.com/apikey](https://aistudio.google.com/apikey), variable `GEMINI_API_KEY`). Si Gemini no está configurado, falla o agota su cuota, la tool cae automáticamente a **[Pollinations.ai](https://pollinations.ai)**: gratis, sin API key, sin cuenta y sin caducidad, así que `generate_image` siempre tiene un proveedor funcional.

- Acepta un prompt en inglés (puede incluir texto corto a renderizar dentro de la imagen) y `aspect_ratio` (1:1, 16:9, 9:16, etc.)
- Si WordPress está activado, sube la imagen a su mediateca y devuelve una **URL pública estable**, directamente usable como `image_url` en Instagram, Facebook, LinkedIn y Threads
- Es el **proveedor de imágenes por defecto** del flujo de `adhoc-publisher`; Canva queda como último fallback manual si `generate_image` falla del todo (ver su CLAUDE.md, PASO 5)

---

## Configuración en Claude Desktop / Claude Code

Un único entry point para todas las plataformas API. Las credenciales se pueden configurar de **tres formas equivalentes** (el código lee primero las variables de entorno y luego el `.env`):

1. **Bloque `"env"` del config del cliente MCP** — recomendado para uso local
2. **Variables de entorno del dashboard de Render** — para despliegue remoto
3. **Archivo `unified-mcp/.env`** — para desarrollo

### Uso local (stdio)

```json
{
  "mcpServers": {
    "social-mcp": {
      "command": "python",
      "args": ["/ruta/absoluta/social-mcps/unified-mcp/server.py"],
      "env": {
        "WP_ACCESS_TOKEN": "tu_token",
        "WP_SITE_ID": "12345678",
        "LINKEDIN_ACCESS_TOKEN": "...",
        "ENABLE_THREADS": "false"
      }
    },
    "social-automation": {
      "command": "node",
      "args": ["/ruta/absoluta/social-mcps/social-automation-mcp/build/index.js"]
    }
  }
}
```

El bloque `"env"` es opcional si ya tienes un `.env` en `unified-mcp/`. `social-automation` es opcional si no necesitas publicar en X ni compartir en el feed personal de Facebook desde el equipo local.

**Windows** — rutas con barras normales o dobles barras invertidas:
```json
"args": ["C:/Users/TuUsuario/social-mcps/unified-mcp/server.py"]
```

**Windows + Microsoft Store**: si `python` en PATH resuelve al alias de Microsoft Store (`AppData\Local\Microsoft\WindowsApps\python.exe`), el proceso falla al arrancar aunque exista una instalación real de Python. Usa el lanzador `py` en su lugar (resuelve al intérprete real):

```json
"command": "py",
"args": ["-3", "/ruta/absoluta/social-mcps/unified-mcp/server.py"]
```

### Elegir local vs online (cada agente, cada vez)

`unified-mcp` puede arrancar en dos modos (`stdio` local o `streamable-http` remoto) sin cambiar código — la elección es puramente de configuración del cliente MCP:

- **`social-mcps-local`** — definido en [`.mcp.json`](.mcp.json) en la raíz del repo (control de versiones, sin secretos: usa `unified-mcp/.env` local para credenciales). Claude Code lo detecta automáticamente al abrir este proyecto y pedirá aprobarlo la primera vez. Gratis, requiere el PC encendido.
- **`social-mcps-online`** *(o `social-mcps`, según cuándo se añadió)* — definido en la config de usuario de Claude Code (`~/.claude.json`, fuera del repo) o como conector remoto en ChatGPT/otra app, apuntando al gateway Cloudflare → Cloud Run. Funciona con el PC apagado; tiene coste de infraestructura (ver más abajo).

Como cada servidor tiene un nombre distinto, sus herramientas quedan namespaced por separado (`mcp__social-mcps-local__*` vs `mcp__social-mcps-online__*`) — pueden estar los dos activos a la vez sin colisión. Para elegir cuál usar en un momento dado:

- **Claude Code**: usa `/mcp` para habilitar/deshabilitar cada servidor en la sesión, o simplemente indica en el prompt cuál usar (p. ej. "usa social-mcps-local para esto").
- **ChatGPT / otras apps de conectores**: no leen `.mcp.json`; registra ambos como conectores separados (uno local si la app soporta comandos locales, uno remoto con la URL del gateway) y activa/desactiva el que corresponda desde su propio selector de herramientas/conectores por conversación.

### Uso remoto (Cloud Run + gateway Cloudflare)

Añade el servidor como conector MCP remoto en cualquier app que lo soporte (Claude, ChatGPT, etc.):

- **URL**: la URL del gateway Cloudflare (`https://social-mcps.<subdominio>.workers.dev/mcp` o el dominio público, ver `docs/superpowers/plans/2026-08-03-cloud-run-social-mcp.md`)
- **Header de autenticación**: `Authorization: Bearer <token>`

Sin ese header, el servidor responde `401 Unauthorized`. `render.yaml` documenta una ruta de despliegue alternativa en Render, pero la fuente de verdad actual del despliegue remoto es Google Cloud Run + Cloudflare (ver sección siguiente).

---

## Activar y desactivar plataformas

Cada plataforma se activa o desactiva en `unified-mcp/.env` con una variable `ENABLE_*`. Las plataformas desactivadas no registran sus herramientas en el servidor MCP — el agente simplemente no las ve.

```env
ENABLE_LINKEDIN=true
ENABLE_INSTAGRAM=true
ENABLE_FACEBOOK=true
ENABLE_THREADS=true
ENABLE_WORDPRESS=true
ENABLE_X=true
ENABLE_FB_SHARE=true
```

Todas están activadas por defecto. Una plataforma desactivada no registra sus tools ni valida sus credenciales — útil para empezar con una sola red configurada o para apagar temporalmente una plataforma con el token caducado.

---

## Arquitectura

```
social-mcps/
├── unified-mcp/                    ← Servidor unificado (Render-compatible)
│   ├── server.py                   ← Entry point FastMCP, transport streamable-http
│   ├── core/
│   │   ├── logger.py               ← Logger compartido
│   │   ├── models.py               ← ToolResult + modelos Pydantic de cada plataforma
│   │   └── retry.py                ← Decoradores de reintentos (backoff exponencial)
│   ├── auth/                       ← Gestores de tokens por plataforma
│   ├── clients/                    ← Clientes HTTP por plataforma + x_twikit.py
│   ├── tools/                      ← Handlers de herramientas MCP
│   │   ├── fb_share.py             ← Stub: redirige a notifier (requiere Playwright local)
│   │   └── x.py                    ← Post via Twikit; fallo → notifier
│   ├── notifier.py                 ← Alerta estructurada cuando se necesita acción manual
│   ├── .env.example                ← Todas las variables (todas las plataformas)
│   └── render.yaml                 ← Despliegue en Render
│
├── social-automation-mcp/          ← Automatización local con Playwright
│   └── src/tools/
│       ├── post-to-x.ts            ← post_to_x via Chromium (fallback cuando Twikit falla)
│       └── share-to-fb-feed.ts     ← share_to_fb_feed via Chromium (única opción disponible)
│
├── linkedin/                       ← Servidor independiente legacy (uso local standalone)
├── instagram/                      ← Servidor independiente legacy
├── facebook/                       ← Servidor independiente legacy
├── threads/                        ← Servidor independiente legacy
└── wordpress/                      ← Servidor independiente legacy
```

Los servidores individuales de cada plataforma (`linkedin/`, `instagram/`, etc.) siguen funcionando de forma standalone para uso local. El servidor unificado es el modo de uso recomendado.

---

## Primeros pasos

### 1. Configurar credenciales

```bash
cd unified-mcp
cp .env.example .env
```

Edita `.env` con las credenciales de cada plataforma que quieras usar. Consulta el README de la carpeta de cada plataforma para el proceso de obtención de tokens.

### 2. Instalar dependencias

```bash
cd unified-mcp
pip install -r requirements.txt
```

### 3. Arrancar el servidor unificado

```bash
python unified-mcp/server.py
```

### 4. (Opcional) Configurar social-automation-mcp

Solo necesario si vas a publicar en X desde local o compartir en el feed personal de Facebook:

```bash
cd social-automation-mcp
npm install
npm run build
npm run setup-x     # guarda sesión de X en auth/x-session.json
npm run setup-fb    # guarda sesión de Facebook en auth/fb-session.json
```

---

## Despliegue en Google Cloud Run + Cloudflare (producción actual)

El servidor online real corre en Cloud Run (proyecto `socialmcps`, región `europe-west1`, servicio `unified-mcp`), detrás de un Worker de Cloudflare (`social-mcps`) que hace de gateway/auth — ver `docs/superpowers/plans/2026-08-03-cloud-run-social-mcp.md` y el issue de dominio propio.

**Credenciales**: viven en un único secreto de Secret Manager, `social-mcps-credentials` (JSON con todas las credenciales de plataforma + `MCP_AUTH_TOKEN`), inyectado a Cloud Run como la variable `SOCIAL_MCPS_SECRETS_JSON`. `core/config.py::load_consolidated_secrets()` lo desempaqueta a variables de entorno individuales al arrancar — el resto del código no distingue de dónde vino cada credencial. Antes había 29 secretos individuales; se consolidaron en uno para no pasarse del free tier de Secret Manager (6 versiones activas). Ver `deploy/google-cloud/rotate-secret.sh` para rotar un campo sin volver a crear 29 secretos.

Redeploy típico (rebuild desde código + mismas variables/secretos):

```bash
gcloud run deploy unified-mcp --source unified-mcp \
  --project=socialmcps --region=europe-west1
```

## Despliegue en Render (alternativa)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/danilotestoni/social-mcps)

Cada usuario despliega **su propia instancia** con sus propias credenciales — nadie comparte servidor ni tokens. El botón usa el `render.yaml` del repositorio:

1. Haz clic en el botón (necesitas cuenta en Render, el plan free es suficiente)
2. Render crea el servicio y **genera automáticamente un `MCP_AUTH_TOKEN` aleatorio**
3. Rellena en el dashboard (Environment) las credenciales de las plataformas que uses y pon `ENABLE_*=false` en las que no
4. Copia la URL del servicio + el `MCP_AUTH_TOKEN` en tu app (ver "Uso remoto" arriba)

El servidor arranca con transport `streamable-http` (variable `MCP_TRANSPORT`) para ser accesible como endpoint HTTP desde cualquier agente remoto. En local, sin esa variable, arranca en modo `stdio` para clientes MCP de escritorio.

**Seguridad**: toda petición HTTP debe llevar `Authorization: Bearer <MCP_AUTH_TOKEN>`; sin él el servidor responde 401. Los tokens de las plataformas nunca viajan en URLs (van en headers), por lo que no aparecen en logs ni en mensajes de error.

`social-automation-mcp` **no se puede desplegar en Render** (Chromium no cabe en el plan gratuito). Cuando una acción requiere Playwright desde el servidor en la nube, `notifier.py` devuelve un error estructurado con instrucciones para ejecutarla manualmente desde local.

---

## Principios de diseño

- **Sin credenciales en código:** todo en `.env`, nunca en el repositorio.
- **Reintentos automáticos:** backoff exponencial (2s → 4s → 8s, 3 intentos) en todas las llamadas a API.
- **Respuestas estructuradas:** todas las herramientas devuelven `{"success": true/false, "data": ..., "error": ...}`.
- **Degradación controlada:** cuando una acción no puede ejecutarse en la nube (Playwright), el servidor devuelve un error claro con el payload y la acción a ejecutar manualmente.
- **Dry-run:** todas las herramientas aceptan `dry_run=true` para validar el payload sin publicar nada.
