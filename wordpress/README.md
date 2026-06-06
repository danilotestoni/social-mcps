# WordPress MCP

MCP server para publicar automáticamente en un sitio WordPress.com usando la REST API v1.1 con OAuth 2.0. Se integra con cualquier cliente MCP (Claude Desktop, agentes propios, etc.) y expone cuatro herramientas que el agente puede invocar directamente.

**Importante:** Este MCP funciona con sitios alojados en **WordPress.com** (el servicio gestionado). No es compatible con instalaciones self-hosted de WordPress.org, que usan una API diferente.

## Qué hace

| Herramienta | Descripción |
|---|---|
| `publish_post` | Crea un post en el sitio con título, contenido y estado (publicado, borrador o privado). Admite imagen destacada desde URL pública o archivo local |
| `get_last_posts` | Devuelve los últimos N posts del sitio |
| `delete_post` | Elimina un post por su ID numérico |
| `get_account_info` | Devuelve información del sitio (nombre, URL, descripción, número de posts) |

El MCP recibe el contenido ya formateado. Puedes pasar HTML en el campo `content` o texto plano; WordPress lo renderizará tal cual.

---

## Requisitos previos

- Python 3.11 o superior
- Una cuenta WordPress.com con al menos un sitio
- Una WordPress.com Developer App (ver Fase 1)

---

## Fase 1 — Crear la app en WordPress.com Developer Portal

Este paso es manual y solo se hace una vez. Es el más sencillo de los cuatro MCPs: sin procesos de revisión, sin restricciones de tipo de cuenta.

### 1.1 Crear la aplicación

1. Ve a [developer.wordpress.com/apps](https://developer.wordpress.com/apps) e inicia sesión con tu cuenta WordPress.com.
2. Haz clic en **Create New Application**.
3. Rellena los campos:
   - **Name**: el nombre que quieras (p.ej. `social-mcps`)
   - **Description**: una descripción breve
   - **Website URL**: cualquier URL válida (puede ser la de tu sitio)
   - **Redirect URL**: exactamente esta:
     ```
     https://wordpress.com/
     ```
   - **Javascript Origins**: déjalo vacío
   - **Type**: selecciona **Web**
4. Haz clic en **Create**.

### 1.2 Copiar las credenciales

Una vez creada, verás la página de detalle de tu app con:
- **Client ID** → `WP_CLIENT_ID`
- **Client Secret** → `WP_CLIENT_SECRET`

No hay que activar productos adicionales ni solicitar permisos especiales. El scope `global` que usa el script da acceso completo a tu cuenta.

---

## Fase 2 — Configuración inicial (oauth_setup.py)

```bash
cd wordpress
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y rellena `WP_CLIENT_ID` y `WP_CLIENT_SECRET`. Deja el resto vacío.

Luego ejecuta el asistente de autorización:

```bash
python oauth_setup.py
```

El script te guiará para:
1. Abrir la URL de autorización en el navegador
2. Aprobar el acceso en WordPress.com
3. Pegar el código o la URL de redirección (`https://wordpress.com/?code=...`)
4. Listar tus sitios y seleccionar el correcto (si tienes varios)
5. Escribir el access token y el site ID en `.env`

Al terminar, el `.env` quedará completo con `WP_ACCESS_TOKEN` y `WP_SITE_ID`.

---

## Arrancar el servidor

```bash
python server.py
```

---

## Configuración en el cliente MCP

### Claude Desktop

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

Los tokens de WordPress.com son **permanentes**: no tienen fecha de caducidad y no necesitan renovación periódica. El servidor no necesita ningún mecanismo de refresh.

Para revocar el acceso manualmente: [wordpress.com/me/security/connected-applications](https://wordpress.com/me/security/connected-applications)

Si revocas el acceso o el token deja de funcionar por cualquier motivo, vuelve a ejecutar `oauth_setup.py` para obtener uno nuevo.

---

## Publicación con imagen destacada

Cuando se proporciona una imagen, el MCP la sube primero como media y luego la asigna como `featured_image` del post:

```
image_path="/ruta/imagen.jpg"
  → Lee el archivo en binario
  → POST /sites/{id}/media/new  (subida multipart)
  → Obtiene el media ID
  → POST /sites/{id}/posts/new con featured_image=<media_id>

image_url="https://..."
  → Descarga la imagen
  → Mismo proceso de subida y asignación
```

Cuando se proporcionan ambos, `image_path` tiene prioridad sobre `image_url`.

---

## Estados de publicación

El parámetro `status` en `publish_post` acepta tres valores:

| Valor | Efecto |
|---|---|
| `publish` | Publica el post inmediatamente (por defecto) |
| `draft` | Lo guarda como borrador, no visible públicamente |
| `private` | Lo publica pero solo visible para administradores del sitio |

---

## Logs

Los errores y eventos se registran en `logs/wordpress.log` con rotación automática (5 MB × 3 archivos).
