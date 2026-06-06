# Instagram MCP

MCP server para publicar automáticamente en Instagram usando la Instagram Graph API con Facebook Login. Se integra con cualquier cliente MCP (Claude Desktop, agentes propios, etc.) y expone cuatro herramientas que el agente puede invocar directamente.

**Requisito importante:** Necesitas una cuenta Instagram de tipo **Business** o **Creator** vinculada a una Facebook Page. Las cuentas personales de Instagram no tienen acceso a la Graph API de publicación.

## Qué hace

| Herramienta | Descripción |
|---|---|
| `publish_post` | Publica una foto en Instagram con caption. Requiere una URL pública de imagen |
| `get_last_posts` | Devuelve los últimos N posts del perfil autenticado |
| `delete_post` | Elimina un post por su media ID |
| `get_account_info` | Devuelve información del perfil (username, nombre, seguidores, número de posts) |

El MCP recibe el contenido ya formateado (caption con hashtags incluidos). No adapta ni transforma texto.

> **Limitación de la API:** Instagram Graph API solo acepta imágenes como URL públicas accesibles desde internet. No es posible subir binarios directamente para posts de feed. Si pasas `image_path`, el servidor lo indicará con un error claro.

---

## Requisitos previos

- Python 3.11 o superior
- Una cuenta Instagram Business o Creator
- Una Facebook Page vinculada a esa cuenta Instagram
- Una Meta (Facebook) Developer App (ver Fase 1)

---

## Fase 1 — Crear la app en Meta for Developers

Este paso es manual y solo se hace una vez. Obtienes el `APP_ID` y `APP_SECRET`.

### 1.1 Crear la aplicación

1. Ve a [developers.facebook.com](https://developers.facebook.com) e inicia sesión con tu cuenta de Facebook.
2. Haz clic en **My Apps → Create App**.
3. Selecciona el tipo **Business** (es el que da acceso a la Instagram Graph API).
4. Rellena el nombre de la app y el email de contacto.
5. Haz clic en **Create App**.

### 1.2 Añadir el producto Instagram Graph API

1. En el panel de la app, busca **Add a Product**.
2. Busca **Instagram** y haz clic en **Set Up**.
3. Esto activa la Instagram Graph API en tu app.

### 1.3 Vincular tu cuenta Instagram a una Facebook Page

Si aún no lo has hecho:

1. En Instagram, ve a **Configuración → Cuenta → Cambiar a cuenta profesional** y elige Business o Creator.
2. Cuando te pida vincular una Facebook Page, selecciona la tuya o crea una nueva.

Para verificar que está vinculada: en Facebook, ve a tu Page → **Configuración → Instagram** y deberías ver tu cuenta conectada.

### 1.4 Configurar la URL de redirección

1. En el panel de tu app Meta, ve a **Facebook Login → Configuración**.
2. En **Valid OAuth Redirect URIs**, añade:
   ```
   https://www.facebook.com/connect/login_success.html
   ```
3. Guarda los cambios.

### 1.5 Permisos necesarios

En el modo de desarrollo (Development Mode), tienes acceso a estos permisos sin revisión, pero **solo para cuentas que sean administradoras de la app**:

- `instagram_basic`
- `instagram_content_publish`
- `pages_show_list`
- `pages_read_engagement`

Para usar la app con cuentas que no son administradoras, necesitarías pasar el proceso de **App Review** en Meta. Para uso personal o de un equipo pequeño donde todos son admins de la app, el modo desarrollo es suficiente.

### 1.6 Copiar las credenciales

En **Configuración → Básico**, copia:
- **App ID** → `INSTAGRAM_APP_ID`
- **App Secret** → `INSTAGRAM_APP_SECRET`

---

## Fase 2 — Configuración inicial (oauth_setup.py)

```bash
cd instagram
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y rellena `INSTAGRAM_APP_ID` y `INSTAGRAM_APP_SECRET`. Deja el resto vacío.

Luego ejecuta el asistente de autorización:

```bash
python oauth_setup.py
```

El script te guiará para:
1. Abrir la URL de autorización en el navegador
2. Aprobar los permisos con tu cuenta de Facebook
3. Pegar el código o la URL de redirección
4. Detectar automáticamente tu Facebook Page e Instagram Business Account
5. Escribir el Page Access Token y el Account ID en `.env`

Al terminar, el `.env` quedará completo con `INSTAGRAM_ACCESS_TOKEN` (tipo Page Token), `INSTAGRAM_TOKEN_EXPIRY=0` (nunca caduca) e `INSTAGRAM_ACCOUNT_ID`.

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
    "instagram": {
      "command": "python",
      "args": ["/ruta/absoluta/a/social-mcps/instagram/server.py"]
    }
  }
}
```

---

## Tokens y renovación

El script guarda un **Page Access Token**, que no caduca mientras la app esté activa y el usuario no revoque el acceso. No es necesaria ninguna renovación periódica.

Si en algún momento la app pierde acceso (el usuario revoca permisos, la app es suspendida, etc.), vuelve a ejecutar `oauth_setup.py`.

---

## Flujo de publicación

Instagram requiere dos pasos para publicar (a diferencia de otras plataformas):

1. **Crear el container:** se envía la URL de la imagen y el caption. Instagram descarga y procesa la imagen.
2. **Publicar el container:** una vez que el procesamiento termina (estado `FINISHED`), se publica.

El servidor gestiona este ciclo automáticamente, haciendo polling del estado cada 3 segundos hasta un máximo de 60 segundos.

---

## Logs

Los errores y eventos se registran en `logs/instagram.log` con rotación automática (5 MB × 3 archivos).
