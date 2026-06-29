# WordPress MCP

MCP server para publicar automáticamente en un sitio WordPress.com usando la REST API v1.1 con OAuth 2.0. Se integra con cualquier cliente MCP (Claude Desktop, agentes propios, etc.) y expone herramientas que el agente puede invocar directamente.

**Importante:** Este MCP funciona con sitios alojados en **WordPress.com** (el servicio gestionado). No es compatible con instalaciones self-hosted de WordPress.org.

---

## Herramientas disponibles

| Herramienta | Parámetros | Descripción |
|---|---|---|
| `publish_post` | `title` (obligatorio), `content` (obligatorio), `status` (opcional), `image_url` (opcional), `image_path` (opcional) | Crea un post. Si se pasan los dos parámetros de imagen, `image_path` tiene prioridad |
| `get_last_posts` | `count` (opcional, por defecto 10) | Devuelve los últimos N posts del sitio |
| `delete_post` | `post_id` (obligatorio, número entero) | Elimina un post por su ID numérico |
| `get_account_info` | — | Devuelve nombre, URL, descripción y número de posts del sitio |

### Parámetro `status` en `publish_post`

| Valor | Efecto |
|---|---|
| `publish` | Publica el post inmediatamente (valor por defecto) |
| `draft` | Lo guarda como borrador, no visible públicamente |
| `private` | Lo publica pero solo visible para administradores |

### Endpoints de la API que usa este MCP

| Operación | Método | Endpoint |
|---|---|---|
| Info del sitio | GET | `https://public-api.wordpress.com/rest/v1.1/sites/{site-id}` |
| Publicar post | POST | `https://public-api.wordpress.com/rest/v1.1/sites/{site-id}/posts/new` |
| Leer posts | GET | `https://public-api.wordpress.com/rest/v1.1/sites/{site-id}/posts/` |
| Eliminar post | POST | `https://public-api.wordpress.com/rest/v1.1/sites/{site-id}/posts/{post-id}/delete` |
| Subir imagen | POST | `https://public-api.wordpress.com/rest/v1.1/sites/{site-id}/media/new` |
| Listar sitios | GET | `https://public-api.wordpress.com/rest/v1.1/me/sites` |
| Obtener token | POST | `https://public-api.wordpress.com/oauth2/token` |

> **Nota sobre eliminación:** La API REST de WordPress.com usa `POST /{post-id}/delete` en lugar de `HTTP DELETE` — es una particularidad de su API.

### Publicación con imagen destacada

Cuando se proporciona una imagen, el MCP la sube primero y luego la asigna como `featured_image`:

```
image_path="C:/fotos/imagen.jpg"
  → Lee el archivo en binario
  → POST /sites/{id}/media/new  (subida multipart)
  → Obtiene el media ID
  → POST /sites/{id}/posts/new con featured_image=<media_id>

image_url="https://dominio.com/imagen.jpg"
  → Descarga la imagen
  → Mismo proceso de subida y asignación
```

---

## Requisitos previos

- Python 3.11 o superior
- Una cuenta WordPress.com con al menos un sitio
- Una WordPress.com Developer App (ver Fase 1)

---

## Fase 1 — Crear la app en WordPress.com Developer Portal

Es el proceso más sencillo de los cuatro MCPs: sin revisión, sin restricciones.

### 1.1 Crear la aplicación

1. Ve a [developer.wordpress.com/apps](https://developer.wordpress.com/apps) e inicia sesión.
2. Haz clic en **Create New Application**.
3. Rellena los campos:
   - **Name**: el nombre que quieras (p.ej. `social-mcps`)
   - **Description**: descripción breve
   - **Website URL**: la URL de tu sitio
   - **Redirect URL**: exactamente esta:
     ```
     https://wordpress.com/
     ```
   - **Type**: selecciona **Web**
4. Haz clic en **Create**.

### 1.2 Copiar las credenciales

En la página de detalle de la app:
- **Client ID** → `WP_CLIENT_ID`
- **Client Secret** → `WP_CLIENT_SECRET`

---

## Fase 2 — Configuración inicial

```bash
cd wordpress
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y rellena `WP_CLIENT_ID` y `WP_CLIENT_SECRET`. Deja `WP_ACCESS_TOKEN` y `WP_SITE_ID` vacíos.

```bash
python oauth_setup.py
```

El script:
1. Genera la URL de autorización y te la muestra
2. La abres en el navegador y apruebas el acceso en WordPress.com
3. WordPress te redirige a `https://wordpress.com/?code=...` — copia esa URL completa
4. La pegas en la terminal
5. El script lista tus sitios, seleccionas el correcto, y escribe `WP_ACCESS_TOKEN` y `WP_SITE_ID` en `.env`

---

## Arrancar el servidor

```bash
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

Con el servidor principal, las herramientas de WordPress aparecen como `wordpress_publish_post`, `wordpress_get_last_posts`, etc.

**Uso standalone (solo WordPress):** si prefieres arrancar únicamente este servidor de forma independiente:

```json
{
  "mcpServers": {
    "wordpress": {
      "command": "python",
      "args": ["/ruta/absoluta/a/social-mcps/wordpress/server.py"]
    }
  }
}
```

---

## Tokens y renovación

Los tokens de WordPress.com son **permanentes**: no caducan y no necesitan renovación. El servidor no tiene mecanismo de refresh porque no hace falta.

Para revocar el acceso manualmente: [wordpress.com/me/security/connected-applications](https://wordpress.com/me/security/connected-applications)

Si el token deja de funcionar (acceso revocado manualmente), vuelve a ejecutar `oauth_setup.py`.

---

## Logs

`logs/wordpress.log` — rotación automática (5 MB × 3 archivos).
