# Facebook MCP

MCP server para publicar automáticamente en una Facebook Page usando la Pages API con OAuth 2.0. Se integra con cualquier cliente MCP (Claude Desktop, agentes propios, etc.) y expone cuatro herramientas que el agente puede invocar directamente.

**Requisito importante:** Publicas en una **Facebook Page**, no en un perfil personal. Debes ser administrador de la Page.

## Qué hace

| Herramienta | Descripción |
|---|---|
| `publish_post` | Publica un post en la Page: texto solo, imagen desde URL pública, o imagen desde archivo local |
| `get_last_posts` | Devuelve los últimos N posts de la Page |
| `delete_post` | Elimina un post por su ID |
| `get_account_info` | Devuelve información de la Page (nombre, categoría, seguidores, fans) |

El MCP recibe el contenido ya formateado. No adapta ni transforma texto.

A diferencia de Instagram, Facebook sí admite subida binaria de imágenes locales directamente, sin necesidad de URL pública.

---

## Requisitos previos

- Python 3.11 o superior
- Una Facebook Page de la que seas administrador
- Una Meta (Facebook) Developer App (ver Fase 1)

> Si ya configuraste el MCP de Instagram, puedes reutilizar la **misma app de Meta**. Solo necesitas añadir los permisos de Pages que se indican más abajo.

---

## Fase 1 — Crear la app en Meta for Developers

Este paso es manual y solo se hace una vez. Obtienes el `APP_ID` y `APP_SECRET`.

### 1.1 Crear la aplicación (o reutilizar la de Instagram)

**Opción A — App nueva:**
1. Ve a [developers.facebook.com](https://developers.facebook.com) e inicia sesión.
2. Haz clic en **My Apps → Create App**.
3. Selecciona el tipo **Business**.
4. Rellena nombre y email de contacto y haz clic en **Create App**.

**Opción B — Reutilizar la app de Instagram:**
Usa el mismo `APP_ID` y `APP_SECRET`. Solo asegúrate de que la app tiene los permisos de Pages configurados (ver 1.3).

### 1.2 Añadir el producto Facebook Login

1. En el panel de la app, ve a **Add a Product**.
2. Busca **Facebook Login** y haz clic en **Set Up**.
3. Selecciona **Web** como plataforma.

### 1.3 Configurar la URL de redirección

1. En **Facebook Login → Configuración**, añade en **Valid OAuth Redirect URIs**:
   ```
   https://www.facebook.com/connect/login_success.html
   ```
2. Guarda los cambios.

### 1.4 Permisos necesarios

En el modo desarrollo, estos permisos están disponibles sin revisión para las cuentas que son administradoras de la app:

- `pages_manage_posts` — publicar y eliminar posts en la Page
- `pages_read_engagement` — leer posts existentes
- `pages_show_list` — listar las Pages del usuario

Para publicar en producción desde cuentas que no son admins de la app, necesitarás pasar el proceso de **App Review** en Meta y solicitar estos permisos. Para uso personal o en equipo donde todos son admins, el modo desarrollo es suficiente.

### 1.5 Copiar las credenciales

En **Configuración → Básico**, copia:
- **App ID** → `FACEBOOK_APP_ID`
- **App Secret** → `FACEBOOK_APP_SECRET`

---

## Fase 2 — Configuración inicial (oauth_setup.py)

```bash
cd facebook
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y rellena `FACEBOOK_APP_ID` y `FACEBOOK_APP_SECRET`. Deja el resto vacío.

Luego ejecuta el asistente de autorización:

```bash
python oauth_setup.py
```

El script te guiará para:
1. Abrir la URL de autorización en el navegador
2. Aprobar los permisos con tu cuenta de Facebook
3. Pegar el código o la URL de redirección
4. Listar tus Pages y seleccionar la correcta (si tienes varias)
5. Escribir el Page Access Token y el Page ID en `.env`

Al terminar, el `.env` quedará completo con `FACEBOOK_ACCESS_TOKEN` (tipo Page Token), `FACEBOOK_TOKEN_EXPIRY=0` (nunca caduca) y `FACEBOOK_PAGE_ID`.

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
    "facebook": {
      "command": "python",
      "args": ["/ruta/absoluta/a/social-mcps/facebook/server.py"]
    }
  }
}
```

---

## Tokens y renovación

El script guarda un **Page Access Token**, que no caduca mientras la app esté activa y el usuario no revoque el acceso. No es necesaria ninguna renovación periódica.

Si la app pierde acceso (permisos revocados, app suspendida, etc.), vuelve a ejecutar `oauth_setup.py`.

---

## Modos de publicación

```
publish_post(message="Texto del post")
  → POST /{page-id}/feed   (solo texto)

publish_post(message="...", image_url="https://...")
  → POST /{page-id}/photos con url   (imagen desde URL pública)

publish_post(message="...", image_path="/ruta/foto.jpg")
  → POST /{page-id}/photos multipart  (subida binaria directa)
```

Cuando se proporciona `image_path`, tiene prioridad sobre `image_url`.

---

## Logs

Los errores y eventos se registran en `logs/facebook.log` con rotación automática (5 MB × 3 archivos).
