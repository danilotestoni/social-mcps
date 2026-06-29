# Instagram MCP

MCP server para publicar automáticamente en Instagram usando la Instagram Graph API. Se integra con cualquier cliente MCP (Claude Desktop, agentes propios, etc.) y expone herramientas que el agente puede invocar directamente.

**Requisito importante:** Necesitas una cuenta Instagram de tipo **Creator** o **Business** vinculada a una Facebook Page. Las cuentas personales no tienen acceso a la Graph API de publicación.

---

## Herramientas disponibles

| Herramienta | Parámetros | Descripción |
|---|---|---|
| `publish_post` | `caption` (obligatorio), `image_url` (obligatorio) | Publica una foto con caption. Requiere una URL pública de imagen JPEG |
| `get_last_posts` | `count` (opcional, por defecto 10) | Devuelve los últimos N posts del perfil |
| `delete_post` | `media_id` (obligatorio) | Elimina un post por su media ID |
| `get_account_info` | — | Devuelve username, nombre, seguidores y número de posts |

> La Instagram Graph API **solo acepta URLs públicas de imágenes** (no archivos locales) para posts de feed. El formato recomendado es JPEG.

### Flujo de publicación (2 pasos, gestionado automáticamente)

1. **Crear container:** envía la URL de imagen y el caption → Instagram descarga y procesa la imagen
2. **Esperar:** polling del estado cada 3 segundos hasta que sea `FINISHED` (máx. 60 segundos)
3. **Publicar:** envía el container_id para publicarlo definitivamente

---

## Requisitos previos

- Python 3.11 o superior
- Cuenta Instagram Creator o Business **vinculada a una Facebook Page**
- La misma app de Meta for Developers que usas para Facebook

---

## Configuración

### Paso 1 — Verificar cuenta Instagram profesional

Tu cuenta de Instagram debe ser **Creator** o **Business** (no personal):
- Instagram → **Configuración → Cuenta → Tipo de cuenta**
- Si es personal: **Cambiar a cuenta profesional** → selecciona Creator

### Paso 2 — Vincular Instagram a tu Facebook Page

Desde la app de Instagram:
- **Configuración → Cuenta → Cuenta profesional → Página de Facebook vinculada**
- Debe mostrar tu Facebook Page (p. ej. "TechnoLoGeek")
- Si no está vinculada: toca **Crear o conectar página** y selecciona la correcta

### Paso 3 — Obtener tokens via Graph API Explorer

> Usa la **misma app** que para Facebook. El mismo Page Access Token sirve para ambos servidores.

1. Ve a [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)
2. En **Meta App**, selecciona tu app (p. ej. TechnoLoGeek)
3. Haz clic en **Add a Permission** y añade **los 5 permisos**:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
4. Haz clic en **Generate Access Token** y aprueba todos
5. En el campo de URL escribe:
   ```
   /{slug-de-tu-pagina}?fields=id,instagram_business_account,access_token
   ```
   Por ejemplo: `/elsacapuntes?fields=id,instagram_business_account,access_token`
6. Haz clic en **Enviar**
7. Del resultado, copia:
   - `access_token` → `INSTAGRAM_ACCESS_TOKEN`
   - `instagram_business_account.id` → `INSTAGRAM_ACCOUNT_ID`

> **Clave:** El `access_token` de este resultado es un **Page Access Token permanente** con permisos de Instagram heredados del User Token. Nunca caduca.

### Paso 4 — Configurar el .env

```bash
cd instagram
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` con los valores obtenidos:

```env
INSTAGRAM_APP_ID=858814230609482
INSTAGRAM_APP_SECRET=tu_app_secret
INSTAGRAM_ACCESS_TOKEN=EAAMNFkU...  (el access_token del resultado de la consulta)
INSTAGRAM_TOKEN_EXPIRY=0
INSTAGRAM_ACCOUNT_ID=17841400518040781  (el instagram_business_account.id)
```

`INSTAGRAM_TOKEN_EXPIRY=0` indica que el token nunca caduca (Page Access Token permanente).

---

## Arrancar el servidor

```bash
cd instagram
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

Con el servidor unificado, las herramientas de Instagram aparecen como `instagram_publish_post`, `instagram_get_last_posts`, etc.

**Uso standalone (solo Instagram):** si prefieres arrancar únicamente este servidor de forma independiente:

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

El **Page Access Token permanente** no caduca. Solo necesitas renovarlo si:
- Revocast los permisos de la app desde la configuración de Facebook o Instagram
- La app es suspendida por Meta

Si el servidor empieza a dar errores de autenticación (código 190), repite desde el Paso 3.

---

## Logs

`logs/instagram.log` — rotación automática (5 MB × 3 archivos).
