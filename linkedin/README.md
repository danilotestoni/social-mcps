# LinkedIn MCP

MCP server para publicar automáticamente en LinkedIn usando la API de UGC Posts. Se integra con cualquier cliente MCP (Claude Desktop, agentes propios, etc.) y expone cuatro herramientas que el agente puede invocar directamente.

## Qué hace

| Herramienta | Descripción |
|---|---|
| `publish_post` | Publica un post en LinkedIn, con texto solo o con imagen (URL pública o archivo local) |
| `get_last_posts` | Devuelve los últimos N posts del perfil autenticado |
| `delete_post` | Elimina un post por su URN |
| `get_account_info` | Devuelve información del perfil (nombre, headline) |

El MCP recibe el contenido ya formateado. No adapta ni transforma texto. Si el access token está próximo a caducar (menos de 7 días), registra un aviso en el log. Si ya ha caducado, lo renueva automáticamente con el refresh token y actualiza el `.env`.

---

## Requisitos previos

- Python 3.11 o superior
- Una cuenta LinkedIn (personal o de empresa)
- Una LinkedIn Developer App (ver Fase 1)

---

## Fase 1 — Crear la app en LinkedIn Developer Portal

Este paso es manual y solo se hace una vez. Obtienes el `CLIENT_ID` y `CLIENT_SECRET`.

### 1.1 Crear la aplicación

1. Ve a [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps) e inicia sesión.
2. Haz clic en **Create app**.
3. Rellena los campos:
   - **App name**: el nombre que quieras (p.ej. `social-mcps`)
   - **LinkedIn Page**: necesitas asociar una LinkedIn Page. Si no tienes, crea una desde [linkedin.com/company/setup/new](https://www.linkedin.com/company/setup/new) (puede ser una página vacía, solo es un requisito formal).
   - **App logo**: sube cualquier imagen.
4. Acepta los términos y haz clic en **Create app**.

### 1.2 Activar los productos necesarios

En la app recién creada, ve a la pestaña **Products** y solicita acceso a:

- **Share on LinkedIn** — permite publicar posts (`w_member_social`)
- **Sign In with LinkedIn using OpenID Connect** — permite leer el perfil (`r_liteprofile`, `openid`, `profile`, `email`)

Haz clic en **Request access** en cada uno. La aprobación de "Share on LinkedIn" es automática e inmediata.

### 1.3 Configurar la URL de redirección

1. Ve a la pestaña **Auth**.
2. En **Authorized redirect URLs for your app**, añade exactamente esta URL:
   ```
   https://www.linkedin.com/developers/tools/oauth/redirect
   ```
3. Guarda los cambios.

### 1.4 Copiar las credenciales

En la pestaña **Auth**, copia:
- **Client ID** → `LINKEDIN_CLIENT_ID`
- **Client Secret** → `LINKEDIN_CLIENT_SECRET`

> **Nota sobre scopes y app review:** Los scopes `r_liteprofile` y `w_member_social` están disponibles sin revisión manual si has activado los productos de arriba. El scope `r_member_social` (para leer posts propios) requiere el producto **Marketing Developer Platform**, que sí tiene proceso de revisión. Si no lo tienes, `get_last_posts` devolverá un error de permisos — el resto de herramientas funcionará igualmente.

---

## Fase 2 — Configuración inicial (oauth_setup.py)

```bash
cd linkedin
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y rellena `LINKEDIN_CLIENT_ID` y `LINKEDIN_CLIENT_SECRET`. Deja el resto vacío.

Luego ejecuta el asistente de autorización:

```bash
python oauth_setup.py
```

El script te guiará para:
1. Abrir la URL de autorización en el navegador
2. Aprobar los permisos en LinkedIn
3. Pegar el código o la URL de redirección
4. Obtener los tokens y escribirlos automáticamente en `.env`

Al terminar, el `.env` quedará completo con `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_REFRESH_TOKEN`, `LINKEDIN_TOKEN_EXPIRY` y `LINKEDIN_PERSON_URN`.

---

## Arrancar el servidor

```bash
python server.py
```

El servidor arranca en modo stdio y queda a la espera de llamadas MCP.

---

## Configuración en el cliente MCP

### Claude Desktop

Añade esto a `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) o `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "linkedin": {
      "command": "python",
      "args": ["/ruta/absoluta/a/social-mcps/linkedin/server.py"]
    }
  }
}
```

Reinicia Claude Desktop. El servidor aparecerá disponible en la interfaz.

---

## Tokens y renovación automática

| Token | Duración | Gestión |
|---|---|---|
| Access token | 60 días | Se renueva automáticamente si hay refresh token válido |
| Refresh token | 365 días | Se renueva al usarlo |

Si el refresh token también ha caducado (sin actividad durante más de 365 días), el servidor devolverá un error de autenticación. En ese caso, vuelve a ejecutar `oauth_setup.py`.

---

## Logs

Los errores y eventos se registran en `logs/linkedin.log` con rotación automática (5 MB × 3 archivos). El servidor escribe a `stderr` en lugar de `stdout` para no interferir con el protocolo MCP stdio.
