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

---

## Configuración en Claude Desktop / Claude Code

Un único entry point para todas las plataformas API:

```json
{
  "mcpServers": {
    "social-mcp": {
      "command": "python",
      "args": ["/ruta/absoluta/social-mcps/unified-mcp/server.py"]
    },
    "social-automation": {
      "command": "node",
      "args": ["/ruta/absoluta/social-mcps/social-automation-mcp/build/index.js"]
    }
  }
}
```

`social-automation` es opcional si no necesitas publicar en X ni compartir en el feed personal de Facebook desde el equipo local.

**Windows** — rutas con barras normales o dobles barras invertidas:
```json
"args": ["C:/Users/TuUsuario/social-mcps/unified-mcp/server.py"]
```

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
```

Útil para deshabilitar temporalmente una plataforma con token caducado sin tener que detener el servidor.

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

## Despliegue en Render

El archivo `unified-mcp/render.yaml` configura el despliegue automático. El servidor arranca con transport `streamable-http` para ser accesible como endpoint HTTP desde cualquier agente remoto.

`social-automation-mcp` **no se puede desplegar en Render** (Chromium no cabe en el plan gratuito). Cuando una acción requiere Playwright desde el servidor en la nube, `notifier.py` devuelve un error estructurado con instrucciones para ejecutarla manualmente desde local.

---

## Principios de diseño

- **Sin credenciales en código:** todo en `.env`, nunca en el repositorio.
- **Reintentos automáticos:** backoff exponencial (2s → 4s → 8s, 3 intentos) en todas las llamadas a API.
- **Respuestas estructuradas:** todas las herramientas devuelven `{"success": true/false, "data": ..., "error": ...}`.
- **Degradación controlada:** cuando una acción no puede ejecutarse en la nube (Playwright), el servidor devuelve un error claro con el payload y la acción a ejecutar manualmente.
- **Dry-run:** todas las herramientas aceptan `dry_run=true` para validar el payload sin publicar nada.
