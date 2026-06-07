# Threads MCP

MCP server para publicar automáticamente en Threads usando la Threads API v1.0. Se integra con cualquier cliente MCP (Claude Desktop, agentes propios, etc.) y expone herramientas que el agente puede invocar directamente.

---

## Herramientas disponibles

| Herramienta | Parámetros | Descripción |
|---|---|---|
| `publish_post` | `text` (obligatorio), `image_url` (opcional) | Publica un post en Threads. Sin imagen = post de texto; con imagen = post con foto |
| `get_last_posts` | `count` (opcional, por defecto 10) | Devuelve los últimos N posts del perfil |
| `delete_post` | `thread_id` (obligatorio) | Elimina un post por su ID (requiere permiso `threads_delete`) |
| `get_account_info` | — | Devuelve id, username y nombre del perfil |

> **Nota sobre delete:** Por defecto el token tiene `threads_basic` y `threads_content_publish`. Para usar `delete_post` vía API necesitas añadir `threads_delete` a los permisos de tu app y regenerar el token con `oauth_setup.py`.

### Flujo de publicación (2 pasos, gestionado automáticamente)

1. **Crear container:** envía el texto e imagen opconal → Threads prepara el contenido
2. **Publicar:** envía el container_id → el post aparece en el feed

---

## Requisitos previos

- Python 3.11 o superior
- Cuenta de Threads pública
- App en Meta for Developers con el producto **Threads API** habilitado

---

## Configuración

### Paso 1 — Crear la app en Meta for Developers (solo la primera vez)

1. Ve a [developers.facebook.com](https://developers.facebook.com) e inicia sesión.
2. **My Apps → Create App → tipo Business** (o usa una app existente).
3. En **Add a Product** añade **Threads API**.
4. En la sección Threads API, añade los permisos: `threads_basic`, `threads_content_publish`.
5. Añade tu cuenta de Threads como usuario de prueba.

### Paso 2 — Obtener el token de acceso de larga duración

#### Método A: Panel de Meta (recomendado si tienes el token)

En el panel de tu app → **Threads API** → **Genera identificadores de acceso**:
- Copia el **identificador de acceso de larga duración** → `THREADS_ACCESS_TOKEN`
- El **identificador de usuario** aparece en la misma sección → `THREADS_USER_ID`

> Los tokens de larga duración son válidos **60 días** y se renuevan automáticamente con `oauth_setup.py`.

#### Método B: oauth_setup.py (para regenerar cuando caduque)

```bash
# Añade http://localhost:8888/callback a los redirect URIs de tu app primero
cd threads
python oauth_setup.py
```

El script abre el navegador, autoriza, intercambia por token de larga duración y guarda todo en `.env`.

### Paso 3 — Configurar el .env

```bash
cd threads
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env`:

```env
THREADS_APP_ID=2488607828267571
THREADS_APP_SECRET=tu_app_secret
THREADS_ACCESS_TOKEN=THAAj...  (token de larga duración del panel)
THREADS_TOKEN_EXPIRY=1754524800  (hoy + 60 días en Unix timestamp)
THREADS_USER_ID=25012933805070903  (ID numérico de tu cuenta)
```

Para calcular `THREADS_TOKEN_EXPIRY`: `date +%s` + `5184000` (60 días en segundos).

---

## Arrancar el servidor

```bash
cd threads
python server.py
```

---

## Configuración en Claude Desktop

```json
{
  "mcpServers": {
    "threads": {
      "command": "python",
      "args": ["/ruta/absoluta/a/social-mcps/threads/server.py"]
    }
  }
}
```

---

## Tokens y renovación

Los tokens de Threads duran **60 días**. El servidor los renueva automáticamente si no han caducado todavía (llamando a `GET /refresh_access_token?grant_type=th_refresh_token`).

Si el token caduca sin renovarse, ejecuta `oauth_setup.py` para obtener uno nuevo.

---

## Logs

`logs/threads.log` — rotación automática (5 MB × 3 archivos).
