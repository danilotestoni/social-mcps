# LinkedIn MCP

MCP server para publicar automáticamente en LinkedIn usando la API de UGC Posts. Se integra con cualquier cliente MCP (Claude Desktop, agentes propios, etc.) y expone herramientas que el agente puede invocar directamente.

---

## Herramientas disponibles

| Herramienta | Parámetros | Descripción |
|---|---|---|
| `publish_post` | `text` (obligatorio), `image_url` (opcional), `image_path` (opcional) | Publica un post. Si se pasan los dos parámetros de imagen, `image_path` tiene prioridad |
| `get_last_posts` | `count` (opcional, por defecto 10) | Devuelve los últimos N posts del perfil autenticado |
| `delete_post` | `post_urn` (obligatorio) | Elimina un post por su URN (p.ej. `urn:li:ugcPost:123456789`) |
| `get_account_info` | — | Devuelve id, nombre y URN del perfil autenticado |

### Endpoints de la API que usa este MCP

| Operación | Método | Endpoint |
|---|---|---|
| Perfil | GET | `https://api.linkedin.com/v2/userinfo` |
| Publicar post | POST | `https://api.linkedin.com/v2/ugcPosts` |
| Leer posts | GET | `https://api.linkedin.com/v2/ugcPosts?q=authors` |
| Eliminar post | DELETE | `https://api.linkedin.com/v2/ugcPosts/{urn}` |
| Registrar subida imagen | POST | `https://api.linkedin.com/v2/assets?action=registerUpload` |
| Subir imagen | PUT | URL presignada devuelta por el registro |
| Renovar token | POST | `https://www.linkedin.com/oauth/v2/accessToken` |

> **Nota:** `get_last_posts` requiere el producto **Marketing Developer Platform** en tu app LinkedIn (tiene proceso de revisión). Si no lo tienes, devuelve error 403 — el resto de herramientas funciona igualmente.

---

## Requisitos previos

- Python 3.11 o superior
- Una cuenta LinkedIn (personal o de empresa)
- Una LinkedIn Developer App (ver Fase 1)

---

## Fase 1 — Crear la app en LinkedIn Developer Portal

### 1.1 Crear la aplicación

1. Ve a [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps) e inicia sesión.
2. Haz clic en **Create app**.
3. Rellena:
   - **App name**: el nombre que quieras (p.ej. `social-mcps`)
   - **LinkedIn Page**: asocia cualquier LinkedIn Page. Si no tienes, crea una en [linkedin.com/company/setup/new](https://www.linkedin.com/company/setup/new) — puede estar vacía, es solo un requisito formal.
   - **App logo**: sube cualquier imagen.
4. Acepta los términos y haz clic en **Create app**.

### 1.2 Activar los productos necesarios

En la pestaña **Products**, solicita acceso a:

- **Share on LinkedIn** — aprobación automática e inmediata
- **Sign In with LinkedIn using OpenID Connect** — aprobación automática e inmediata

Sin estos dos productos el OAuth fallará con error de scope no autorizado.

### 1.3 Configurar la URL de redirección

1. Ve a la pestaña **Auth**.
2. En **Authorized redirect URLs for your app**, añade:
   ```
   https://www.linkedin.com/developers/tools/oauth/redirect
   ```
3. Guarda los cambios.

### 1.4 Copiar las credenciales

En la pestaña **Auth**:
- **Client ID** → `LINKEDIN_CLIENT_ID`
- **Client Secret** → `LINKEDIN_CLIENT_SECRET`

---

## Fase 2 — Configuración inicial

```bash
cd linkedin
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y rellena `LINKEDIN_CLIENT_ID` y `LINKEDIN_CLIENT_SECRET`. Deja el resto vacío.

```bash
python oauth_setup.py
```

El script:
1. Genera la URL de autorización y te la muestra
2. Abres la URL en el navegador y apruebas los permisos en LinkedIn
3. LinkedIn te redirige a una página que muestra el código durante 5 segundos — **copia la URL completa de la barra del navegador** antes de que desaparezca
4. Pegas esa URL en la terminal
5. El script obtiene los tokens y escribe en `.env`: `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_REFRESH_TOKEN`, `LINKEDIN_TOKEN_EXPIRY` y `LINKEDIN_PERSON_URN`

### Importante: revisar el LINKEDIN_PERSON_URN

Después del setup, abre `.env` y comprueba que `LINKEDIN_PERSON_URN` tiene el formato completo:
```
LINKEDIN_PERSON_URN=urn:li:person:XXXXXXXXXX
```
Si solo tiene el ID sin el prefijo, añádelo manualmente:
```
LINKEDIN_PERSON_URN=urn:li:person:QYnCA_Ds26
```

---

## Arrancar el servidor

```bash
python server.py
```

---

## Configuración en Claude Desktop

El modo de uso recomendado es a través del **servidor unificado** (`unified-mcp/`), que agrupa todas las plataformas en un único entry point:

```json
{
  "mcpServers": {
    "social-mcp": {
      "command": "python",
      "args": ["/ruta/absoluta/social-mcps/unified-mcp/server.py"]
    }
  }
}
```

Con el servidor unificado, las herramientas de LinkedIn aparecen como `linkedin_publish_post`, `linkedin_get_last_posts`, etc.

**Uso standalone (solo LinkedIn):** si prefieres arrancar únicamente este servidor de forma independiente:

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

En Windows usa barras normales o barras invertidas dobles:
```json
"args": ["C:/Users/TuUsuario/social-mcps/linkedin/server.py"]
```

---

## Tokens y renovación

| Token | Duración | Gestión |
|---|---|---|
| Access token | 60 días | Se renueva automáticamente con el refresh token |
| Refresh token | 365 días | Se renueva al usarlo |

El servidor avisa en el log 7 días antes de que caduque el access token. Si el refresh token también ha caducado (más de 365 días sin usar), vuelve a ejecutar `oauth_setup.py`.

> **Nota:** Algunas apps de LinkedIn no devuelven refresh token en la primera autorización. Si ocurre, el acceso dura 60 días y habrá que volver a ejecutar `oauth_setup.py` al expirar.

---

## Logs

`logs/linkedin.log` — rotación automática (5 MB × 3 archivos). El servidor escribe a `stderr` para no interferir con el protocolo MCP stdio.
