# social-automation-mcp

MCP server for social media automation via browser automation (Playwright + Stealth). Publishes and shares content without needing official API access.

---

## Tools available

| Tool | Description |
|---|---|
| `post_to_x` | Publishes a tweet on X (Twitter) |
| `share_to_fb_feed` | Shares a Facebook page post to your personal feed |

---

## Installation

```bash
cd social-automation-mcp
npm install
npx playwright install chromium
```

---

## Setup inicial (solo una vez por plataforma)

### X (Twitter)

```bash
npm run setup-x
```

1. Se abre Chromium. Inicia sesión manualmente en X.
2. Al llegar a x.com/home, el script guarda la sesión y cierra.
3. Sesión guardada en `auth/x-session.json`.

### Facebook (cuenta personal)

```bash
npm run setup-fb
```

1. Se abre Chromium. Inicia sesión con tu cuenta personal de Facebook.
2. Al salir del flujo de login, el script guarda la sesión y cierra.
3. Sesión guardada en `auth/fb-session.json`.

> Los archivos de sesión contienen cookies. Están en `auth/` que está en `.gitignore` — nunca se suben al repositorio.

---

## Uso desde Claude

**Publicar en X:**
> "Publica en X: Texto del tweet aquí."

**Compartir post de la página en el feed personal:**
> "Comparte este post de Facebook en mi feed personal: https://www.facebook.com/elsacapuntes/posts/123..."

Puedes combinar ambas cosas en una sola instrucción:
> "Publica el último post de elsacapuntes en X y compártelo en tu feed personal de Facebook."

---

## Sobre la detección de bots

Todos los navegadores que lanza este servidor usan `puppeteer-extra-plugin-stealth`, que parchea los indicadores que usan X y Facebook para detectar Playwright:

- `navigator.webdriver` → oculto
- Propiedades del runtime de Chrome → normalizadas
- User-agent → realista
- Plugins y APIs del navegador → con valores reales

Si alguna plataforma empieza a bloquear de nuevo, revisa si hay una versión más nueva de `puppeteer-extra-plugin-stealth`.

---

## Build and run

```bash
npm run build    # compilar TypeScript
npm start        # iniciar el servidor compilado
npm run dev      # dev mode (ts-node, sin compilar)
```

---

## Register in Claude Desktop

**Windows** — `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "social-automation": {
      "command": "node",
      "args": ["D:/DANILO/Documents/PROYECTOS/PERSONALES/PYTHON/social-mcps/social-automation-mcp/build/index.js"]
    }
  }
}
```

Run `npm run build` before restarting Claude Desktop.

---

## Project structure

```
social-automation-mcp/
├── src/
│   ├── index.ts                ← MCP server entry point, tool registration
│   ├── browser.ts              ← shared stealth Chromium instance
│   ├── setup-x-auth.ts         ← one-time X login script
│   ├── setup-fb-auth.ts        ← one-time Facebook login script
│   └── tools/
│       ├── post-to-x.ts        ← post_to_x implementation
│       └── share-to-fb-feed.ts ← share_to_fb_feed implementation
├── auth/                       ← session files (gitignored)
│   ├── x-session.json          ← created by npm run setup-x
│   └── fb-session.json         ← created by npm run setup-fb
├── build/                      ← compiled output (gitignored)
├── package.json
├── tsconfig.json
└── .gitignore
```

---

## Nota sobre selectores

Facebook y X cambian su UI con frecuencia. Los selectores están en:
- `src/tools/post-to-x.ts` — constante `SELECTORS` al inicio del archivo
- `src/tools/share-to-fb-feed.ts` — constante `SELECTORS` al inicio del archivo

Si una tool empieza a fallar con errores de timeout, busca el comentario `TODO: Update these selectors` en el archivo correspondiente y actualiza los valores con las DevTools del navegador.
