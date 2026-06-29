# social-automation-mcp

MCP server de automatización local mediante Playwright + Stealth. Proporciona las herramientas que **no tienen alternativa vía API REST**:

- **`post_to_x`** — Publica un tweet en X (Twitter) usando Chromium. Actúa como fallback cuando Twikit (el cliente ligero del servidor principal) falla.
- **`share_to_fb_feed`** — Comparte un post de una Facebook Page en el feed personal. No existe ninguna API REST para esta acción — Playwright es la única opción.

> **Este servidor es solo local.** Chromium requiere ~826 MB de RAM, incompatible con el plan gratuito de Render (512 MB). El servidor principal (`Social-MCP/`) cubre X via Twikit; cuando Twikit falla o cuando se necesita compartir en Facebook personal, el agente te notifica para que lo ejecutes desde aquí.

---

## Herramientas disponibles

| Herramienta | Parámetros | Descripción |
|---|---|---|
| `post_to_x` | `text` (obligatorio, máx. 280 chars), `dry_run` (opcional) | Publica un tweet usando Chromium con sesión guardada |
| `share_to_fb_feed` | `post_url` (obligatorio), `message` (opcional), `dry_run` (opcional) | Comparte un post de una Page en tu feed personal de Facebook |

---

## Instalación

```bash
cd social-automation-mcp
npm install
npm run build
```

> **No ejecutes** `npx playwright install`. Playwright ya está configurado con Chromium del sistema en el entorno de desarrollo. En local, sí necesitas instalarlo:
> ```bash
> npx playwright install chromium
> ```

---

## Setup inicial (una vez por plataforma)

### X (Twitter)

```bash
npm run setup-x
```

1. Se abre Chromium. Inicia sesión manualmente en X.
2. Al llegar a `x.com/home`, el script guarda la sesión y cierra.
3. Sesión guardada en `auth/x-session.json`.

También puedes importar cookies existentes si ya tienes una sesión exportada:

```bash
npm run import-x-cookies
```

### Facebook (cuenta personal)

```bash
npm run setup-fb
```

1. Se abre Chromium. Inicia sesión con tu cuenta personal de Facebook.
2. Al salir del flujo de login, el script guarda la sesión y cierra.
3. Sesión guardada en `auth/fb-session.json`.

> Las sesiones contienen cookies. La carpeta `auth/` está en `.gitignore` — nunca se sube al repositorio.

---

## Configuración en Claude Desktop

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "social-automation": {
      "command": "node",
      "args": ["/ruta/absoluta/social-mcps/social-automation-mcp/build/index.js"]
    }
  }
}
```

En Windows:
```json
"args": ["C:/Users/TuUsuario/social-mcps/social-automation-mcp/build/index.js"]
```

Ejecuta `npm run build` antes de reiniciar Claude Desktop si hiciste cambios.

Si también tienes el servidor principal, añade ambos:
```json
{
  "mcpServers": {
    "social-mcp": {
      "command": "python",
      "args": ["/ruta/absoluta/social-mcps/Social-MCP/server.py"]
    },
    "social-automation": {
      "command": "node",
      "args": ["/ruta/absoluta/social-mcps/social-automation-mcp/build/index.js"]
    }
  }
}
```

---

## Uso desde Claude

**Publicar en X:**
> "Publica en X: Texto del tweet aquí."

**Compartir post de la página en el feed personal:**
> "Comparte este post de Facebook en mi feed personal: https://www.facebook.com/elsacapuntes/posts/123..."

Puedes combinar ambas:
> "Publica el último post de elsacapuntes en X y compártelo en tu feed personal de Facebook."

---

## Sobre la detección de bots

Todos los navegadores lanzados por este servidor usan `puppeteer-extra-plugin-stealth`, que normaliza los indicadores que X y Facebook usan para detectar Playwright:

- `navigator.webdriver` → oculto
- Propiedades del runtime de Chrome → normalizadas
- User-agent → realista
- Plugins y APIs del navegador → con valores reales

Si una plataforma empieza a bloquear sesiones, revisa si hay una versión más nueva de `puppeteer-extra-plugin-stealth`.

---

## Comandos disponibles

```bash
npm run build           # Compilar TypeScript → build/
npm start               # Iniciar el servidor compilado
npm run dev             # Modo dev (ts-node, sin compilar)
npm run setup-x         # Setup interactivo de sesión de X
npm run setup-fb        # Setup interactivo de sesión de Facebook
npm run import-x-cookies  # Importar cookies de X desde archivo externo
```

---

## Estructura del proyecto

```
social-automation-mcp/
├── src/
│   ├── index.ts                ← Entry point MCP, registro de herramientas
│   ├── browser.ts              ← Instancia de Chromium compartida (stealth)
│   ├── setup-x-auth.ts         ← Script de login inicial en X
│   ├── setup-fb-auth.ts        ← Script de login inicial en Facebook
│   └── tools/
│       ├── post-to-x.ts        ← Implementación de post_to_x
│       └── share-to-fb-feed.ts ← Implementación de share_to_fb_feed
├── auth/                       ← Archivos de sesión (gitignored)
│   ├── x-session.json          ← Creado por npm run setup-x
│   └── fb-session.json         ← Creado por npm run setup-fb
├── build/                      ← Output compilado (gitignored)
├── package.json
├── tsconfig.json
└── .gitignore
```

---

## Mantenimiento de selectores

X y Facebook cambian su UI con frecuencia. Los selectores están definidos en la constante `SELECTORS` al inicio de cada archivo de herramienta:

- `src/tools/post-to-x.ts`
- `src/tools/share-to-fb-feed.ts`

Si una herramienta empieza a fallar con errores de timeout, actualiza los selectores usando las DevTools del navegador.
