# Facebook MCP

MCP server para publicar automáticamente en una Facebook Page usando la Pages API con Graph API v21.0. Se integra con cualquier cliente MCP (Claude Desktop, agentes propios, etc.) y expone herramientas que el agente puede invocar directamente.

**Requisito importante:** Publicas en una **Facebook Page**, no en un perfil personal. Debes ser administrador de la Page.

---

## Herramientas disponibles

| Herramienta | Parámetros | Descripción |
|---|---|---|
| `publish_post` | `message` (obligatorio), `image_url` (opcional), `image_path` (opcional) | Publica un post en la Page. Si se pasan los dos parámetros de imagen, `image_path` tiene prioridad |
| `get_last_posts` | `count` (opcional, por defecto 10) | Devuelve los últimos N posts de la Page |
| `delete_post` | `post_id` (obligatorio) | Elimina un post por su ID (p.ej. `323737177695674_987654321`) |
| `get_account_info` | — | Devuelve nombre, categoría, fans y seguidores de la Page |

A diferencia de Instagram, Facebook **sí admite subida binaria de imágenes locales** directamente desde archivo.

### Endpoints de la API que usa este MCP

| Operación | Método | Endpoint |
|---|---|---|
| Info de la Page | GET | `https://graph.facebook.com/v21.0/{page-id}` |
| Publicar post de texto | POST | `https://graph.facebook.com/v21.0/{page-id}/feed` |
| Publicar foto (URL) | POST | `https://graph.facebook.com/v21.0/{page-id}/photos` con `url` |
| Publicar foto (archivo) | POST | `https://graph.facebook.com/v21.0/{page-id}/photos` multipart con `source` |
| Leer posts | GET | `https://graph.facebook.com/v21.0/{page-id}/posts` |
| Eliminar post | DELETE | `https://graph.facebook.com/v21.0/{post-id}` |

---

## Requisitos previos

- Python 3.11 o superior
- Una Facebook Page de la que seas administrador
- Una app en Meta for Developers (se puede reutilizar la misma que para Instagram)

---

## Configuración

### Paso 1 — Crear la app en Meta for Developers (solo la primera vez)

1. Ve a [developers.facebook.com](https://developers.facebook.com) e inicia sesión.
2. **My Apps → Create App → tipo Business**.
3. Rellena nombre y email.
4. En **Add a Product** añade **Facebook Login → Set Up → Web**.

### Paso 2 — Obtener el Page Access Token via Graph API Explorer

> Este es el método recomendado. Funciona con la app en modo Publicada (producción).

1. Ve a [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)
2. En **Meta App**, selecciona tu app
3. Haz clic en **Add a Permission** y añade:
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `pages_show_list`
   - `instagram_basic` *(añadir también si vas a usar el servidor Instagram)*
   - `instagram_content_publish` *(añadir también si vas a usar el servidor Instagram)*
4. Haz clic en **Generate Access Token** y aprueba todos los permisos
5. En el campo de URL escribe:
   ```
   /{slug-de-tu-pagina}?fields=id,name,access_token
   ```
   Por ejemplo: `/elsacapuntes?fields=id,name,access_token`
6. Haz clic en **Enviar**
7. Del resultado, copia:
   - `id` → `FACEBOOK_PAGE_ID`
   - `access_token` → `FACEBOOK_ACCESS_TOKEN`

> **Nota:** El `access_token` devuelto aquí es un **Page Access Token permanente** (nunca caduca). Es distinto del User Access Token del paso 4. Asegúrate de copiar el del resultado de la consulta, no el del panel superior.

### Paso 3 — Configurar el .env

```bash
cd facebook
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` con los valores obtenidos:

```env
FACEBOOK_APP_ID=858814230609482
FACEBOOK_APP_SECRET=tu_app_secret
FACEBOOK_ACCESS_TOKEN=EAAMNFkU...  (el access_token del resultado de la consulta)
FACEBOOK_TOKEN_EXPIRY=0
FACEBOOK_PAGE_ID=323737177695674  (el id del resultado de la consulta)
```

`FACEBOOK_TOKEN_EXPIRY=0` indica que el token nunca caduca (Page Access Token permanente).

---

## Arrancar el servidor

```bash
cd facebook
python server.py
```

---

## Configuración en Claude Desktop

El modo de uso recomendado es a través del **servidor principal** (`Social-MCP/`), que agrupa todas las plataformas en un único entry point:

```json
{
  "mcpServers": {
    "social-mcp": {
      "command": "python",
      "args": ["/ruta/absoluta/social-mcps/Social-MCP/server.py"]
    }
  }
}
```

Con el servidor principal, las herramientas de Facebook aparecen como `facebook_publish_post`, `facebook_get_last_posts`, etc.

> **Nota:** Este MCP publica en una **Facebook Page** via API REST. Para compartir en el **feed personal** de Facebook necesitas `social-automation-mcp` (Playwright). No existe API REST para esa acción.

**Uso standalone (solo Facebook):** si prefieres arrancar únicamente este servidor de forma independiente:

```json
{
  "mcpServers": {
    "facebook": {
      "command": "python",
      "args": ["/ruta/absoluta/a/social-mcps/facebook/server.py"]
    }
  }
}
```

---

## Tokens y renovación

El **Page Access Token permanente** no caduca. Solo necesitas renovarlo si:
- Revocast los permisos de la app desde la configuración de Facebook
- La app es suspendida por Meta

Si el servidor empieza a dar errores de autenticación, repite el Paso 2 del Graph API Explorer.

---

## Logs

`logs/facebook.log` — rotación automática (5 MB × 3 archivos).
