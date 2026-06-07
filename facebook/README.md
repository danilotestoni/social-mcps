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

### Modos de publicación

```
publish_post(message="Solo texto")
  → POST /{page-id}/feed

publish_post(message="...", image_url="https://dominio.com/foto.jpg")
  → POST /{page-id}/photos con parámetro url

publish_post(message="...", image_path="C:/fotos/imagen.jpg")
  → POST /{page-id}/photos multipart (subida binaria directa)
```

---

## Requisitos previos

- Python 3.11 o superior
- Una Facebook Page de la que seas administrador
- Una app en Meta for Developers

---

## Fase 1 — Crear la app en Meta for Developers

### 1.1 Crear la aplicación

1. Ve a [developers.facebook.com](https://developers.facebook.com) e inicia sesión.
2. **My Apps → Create App → tipo Business**.
3. Rellena nombre y email.

### 1.2 Añadir Facebook Login

En **Add a Product → Facebook Login → Set Up → Web**.

### 1.3 Obtener APP_ID y APP_SECRET

En **Configuración → Básica**:
- **Identificador de la app** → `FACEBOOK_APP_ID`
- **Clave secreta** → `FACEBOOK_APP_SECRET`

---

## Fase 2 — Obtener el Page Access Token

> Con la app en **modo producción (publicada)**, el flujo OAuth con `oauth_setup.py` no funciona (Facebook no permite `localhost` como redirect en producción). El método más fiable es el **Graph API Explorer**.

### Método: Graph API Explorer (recomendado)

1. Ve a [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)
2. En **Aplicación de Meta**, selecciona tu app
3. En el panel **Permissions**, añade:
   - `pages_show_list`
   - `pages_manage_posts`
   - `pages_read_engagement`
4. Haz clic en **Generate Access Token** y aprueba los permisos
5. En el campo de URL escribe:
   ```
   /{slug-de-tu-pagina}?fields=id,name,access_token
   ```
   Por ejemplo: `/elsacapuntes?fields=id,name,access_token`
6. Haz clic en **Enviar**
7. Copia el `access_token` y el `id` del resultado

### Configurar el .env

```bash
cd facebook
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` con los valores obtenidos:

```env
FACEBOOK_APP_ID=tu_app_id
FACEBOOK_APP_SECRET=tu_app_secret
FACEBOOK_ACCESS_TOKEN=el_token_obtenido
FACEBOOK_TOKEN_EXPIRY=0
FACEBOOK_PAGE_ID=el_id_de_la_pagina
```

`FACEBOOK_TOKEN_EXPIRY=0` significa que el token nunca caduca (es un Page Access Token permanente).

> **Atención:** Los tokens generados desde el Graph API Explorer pueden caducar en horas o días si son User Access Tokens, no Page Access Tokens. Si el servidor empieza a dar errores de autenticación, vuelve al explorador y repite el proceso. Para obtener un Page Access Token permanente, la app necesita pasar App Review en Meta para los permisos `pages_manage_posts` y `pages_show_list`.

---

## Arrancar el servidor

```bash
python server.py
```

---

## Configuración en Claude Desktop

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

Con un **Page Access Token permanente** (obtenido de una app con App Review aprobado), no necesitas renovar nunca. Con tokens del Graph API Explorer, actualiza `FACEBOOK_ACCESS_TOKEN` en el `.env` cuando caduquen repitiendo el proceso del explorador.

---

## Logs

`logs/facebook.log` — rotación automática (5 MB × 3 archivos).
