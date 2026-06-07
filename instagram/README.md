# Instagram MCP

MCP server para publicar automáticamente en Instagram usando la Instagram Graph API. Se integra con cualquier cliente MCP (Claude Desktop, agentes propios, etc.) y expone herramientas que el agente puede invocar directamente.

**Requisito importante:** Necesitas una cuenta Instagram de tipo **Business** o **Creator** vinculada a una Facebook Page. Las cuentas personales no tienen acceso a la Graph API de publicación.

---

## Herramientas disponibles

| Herramienta | Parámetros | Descripción |
|---|---|---|
| `publish_post` | `caption` (obligatorio), `image_url` (obligatorio*) | Publica una foto con caption. Requiere una URL pública de imagen |
| `get_last_posts` | `count` (opcional, por defecto 10) | Devuelve los últimos N posts del perfil |
| `delete_post` | `media_id` (obligatorio) | Elimina un post por su media ID |
| `get_account_info` | — | Devuelve username, nombre, seguidores y número de posts |

> \* `image_path` (archivo local) no está soportado por la Instagram Graph API para posts de feed — la API solo acepta URLs públicas accesibles desde internet. Si se pasa `image_path`, el servidor lo indica con un error claro.

### Endpoints de la API que usa este MCP

| Operación | Método | Endpoint |
|---|---|---|
| Info de cuenta | GET | `https://graph.facebook.com/v21.0/{account-id}` |
| Crear container de media | POST | `https://graph.facebook.com/v21.0/{account-id}/media` |
| Estado del container | GET | `https://graph.facebook.com/v21.0/{container-id}?fields=status_code` |
| Publicar container | POST | `https://graph.facebook.com/v21.0/{account-id}/media_publish` |
| Leer posts | GET | `https://graph.facebook.com/v21.0/{account-id}/media` |
| Eliminar post | DELETE | `https://graph.facebook.com/v21.0/{media-id}` |
| Renovar token | GET | `https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token` |

### Flujo de publicación (2 pasos)

Instagram no permite publicar en un solo paso. El servidor lo gestiona automáticamente:

1. **Crear container:** envía la URL de imagen y el caption → Instagram descarga y procesa la imagen
2. **Esperar:** polling del estado cada 3 segundos hasta que sea `FINISHED` (máx. 60 segundos)
3. **Publicar:** envía el container_id para publicarlo definitivamente

---

## Requisitos previos

- Python 3.11 o superior
- Cuenta Instagram Business o Creator vinculada a una Facebook Page
- App en Meta for Developers con Instagram Graph API activado

---

## Fase 1 — Crear la app en Meta for Developers

### 1.1 Crear la aplicación

1. Ve a [developers.facebook.com](https://developers.facebook.com) e inicia sesión.
2. **My Apps → Create App → tipo Business**.
3. Rellena nombre y email de contacto.

### 1.2 Añadir Instagram Graph API

En el panel de la app: **Add a Product → Instagram → Set Up**.

### 1.3 Vincular tu cuenta Instagram

Si tu cuenta de Instagram no es Business o Creator:
1. Instagram → **Configuración → Cuenta → Cambiar a cuenta profesional**
2. Vincula una Facebook Page cuando te lo pida

### 1.4 Obtener APP_ID y APP_SECRET

En **Configuración → Básica**:
- **Identificador de la app** → `INSTAGRAM_APP_ID`
- **Clave secreta** → `INSTAGRAM_APP_SECRET`

---

## Fase 2 — Obtener el token de acceso

> Con la app en **modo producción (publicada)** el flujo OAuth estándar tiene restricciones. El método más fiable es obtener el token directamente desde el panel de Instagram en Meta.

### Método directo desde el panel de Meta (recomendado)

1. En tu app de Meta, ve al producto **Instagram**
2. Busca la sección **"Genera identificadores de acceso"**
3. Añade tu cuenta de Instagram si no está ya
4. Copia el **identificador de acceso** que aparece → `INSTAGRAM_ACCESS_TOKEN`
5. Copia el **ID de cuenta** → `INSTAGRAM_ACCOUNT_ID`

### Configurar el .env

```bash
cd instagram
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` con los valores obtenidos:

```env
INSTAGRAM_APP_ID=tu_app_id
INSTAGRAM_APP_SECRET=tu_app_secret
INSTAGRAM_ACCESS_TOKEN=el_token_obtenido
INSTAGRAM_TOKEN_EXPIRY=1786060800
INSTAGRAM_ACCOUNT_ID=tu_account_id
```

> Para calcular `INSTAGRAM_TOKEN_EXPIRY`: es el timestamp Unix de hoy + 60 días. Los tokens generados desde el panel de Meta tienen una validez aproximada de 60 días.

No hace falta ejecutar `oauth_setup.py` si has seguido el método directo.

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
    "instagram": {
      "command": "python",
      "args": ["/ruta/absoluta/a/social-mcps/instagram/server.py"]
    }
  }
}
```

---

## Tokens y renovación

El servidor comprueba la fecha de expiración antes de cada llamada. Si el token ha caducado, intenta renovarlo automáticamente. Si faltan menos de 7 días para que caduque, registra un aviso en el log.

Cuando el token caduque, vuelve al panel de Meta → Instagram → **Genera identificadores de acceso** y actualiza `INSTAGRAM_ACCESS_TOKEN` en el `.env`.

---

## Logs

`logs/instagram.log` — rotación automática (5 MB × 3 archivos).
