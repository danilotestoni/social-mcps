# ACTUALIZAR-ACCESS-TOKENS.md

Guía completa y secuencial para renovar los access tokens de todas las plataformas de `social-mcps` (LinkedIn, Facebook, Instagram, Threads, WordPress.com y X/Twitter), tanto de forma **automática** (lo que ya hace el propio código) como de forma **manual** (cuando la automática no basta).

---

## 0. Resumen rápido

| Plataforma | Duración del token | ¿Se renueva solo? | Cuándo hace falta manual |
|---|---|---|---|
| LinkedIn | ~60 días | Solo si existe `LINKEDIN_REFRESH_TOKEN` (en nuestra app **no** se emitió) | Cada ~60 días, siempre en nuestro caso actual |
| Facebook (Page token) | Permanente (`expiry=0`) | No hace falta | Solo si se revocan permisos o Meta suspende la app |
| Instagram (Page token) | Permanente (`expiry=0`) | No hace falta | Solo si se revocan permisos o Meta suspende la app |
| Threads | ~60 días | Sí, automático mientras no haya caducado ya (refresco proactivo 7 días antes) | Solo si nadie usa el servidor durante >60 días y caduca sin refrescarse |
| WordPress.com | Permanente | No hace falta | Solo si se revoca el acceso manualmente |
| X/Twitter (Twikit) | No es un token OAuth — login usuario/contraseña | N/A | Si cambias la contraseña, el email, o X pide verificación/challenge |

---

## 1. Mapa de dónde viven las credenciales

Hay **tres** sitios distintos donde puede vivir cada credencial. Hay que mantenerlos sincronizados a mano:

1. **`unified-mcp/.env`** — el que usa el servidor unificado (`social-mcp` en Claude Desktop/Code vía `stdio`). Es el que importa en el día a día local.
2. **`<plataforma>/.env`** (p. ej. `linkedin/.env`, `facebook/.env`...) — usado solo si arrancas esos servidores de forma independiente (standalone), no a través del unificado. Los scripts `oauth_setup.py` de cada carpeta escriben aquí.
3. **Google Secret Manager + Cloud Run** — usado por el despliegue remoto (`unified-mcp` en Cloud Run, proyecto `socialmcps`, región `europe-west1`). Cada variable de entorno del contenedor viene de un secreto (`nombre-en-mayusculas` → `nombre-en-minusculas-con-guiones`).

**Flujo normal para renovar:** obtener el token nuevo (automático o manual) → escribirlo en `unified-mcp/.env` → rotarlo en Secret Manager → forzar redeploy de Cloud Run.

---

## 2. Accesos y herramientas previas necesarias

Antes de tocar nada, comprueba que tienes esto listo:

- **Git Bash** instalado y accesible. Los scripts `.sh` (`oauth_setup.py` puede llamarse con `python`, pero `rotate-secret.sh` es bash puro) **no** funcionan con doble clic en el Explorador de Windows ni con el botón "Run" de VS Code (usa `cmd.exe` y falla con `/usr/bin/env`). Ábrelos siempre desde una terminal Git Bash.
- **gcloud CLI** instalado y autenticado con la cuenta que administra el proyecto:
  ```bash
  gcloud auth login
  gcloud config set project socialmcps
  ```
  Verifica con:
  ```bash
  gcloud config get-value account
  gcloud config get-value project
  ```
- **Python 3.11+** con las dependencias instaladas, tanto en `unified-mcp/` como en la carpeta de la plataforma que vayas a renovar manualmente:
  ```bash
  cd unified-mcp
  pip install -r requirements.txt
  ```
- **Acceso a las cuentas de desarrollador** de cada plataforma (se detalla en la sección 4, por plataforma).

---

## 3. Renovación AUTOMÁTICA

### 3.1 Cómo funciona

Cada plataforma tiene un `TokenManager` en `unified-mcp/auth/<plataforma>_auth.py` con un método `get_valid_token()`. Este método se llama **automáticamente cada vez que se usa cualquier herramienta MCP de esa plataforma** (publicar, leer posts, etc.). Su lógica:

- **Facebook / Instagram**: si el token expira en menos de 7 días, lo refresca con `fb_exchange_token` y lo vuelve a guardar. Si `TOKEN_EXPIRY=0` (permanente), no hace nada.
- **Threads**: igual, pero usando `th_refresh_token`. Solo funciona si el token todavía no ha caducado.
- **LinkedIn**: si el token ha caducado y existe `LINKEDIN_REFRESH_TOKEN`, lo usa para pedir uno nuevo. **En nuestro caso `LINKEDIN_REFRESH_TOKEN` está vacío**, así que esta renovación automática no aplica — LinkedIn requiere manual cada vez (ver 4.1).
- **WordPress**: no hay lógica de refresco, el token es permanente.
- **X**: no hay token, son credenciales de usuario/contraseña.

### 3.2 Comandos para forzar la comprobación/renovación ahora mismo

No hace falta esperar a publicar algo: puedes disparar la comprobación/renovación a mano ejecutando el `TokenManager` directamente. Ejecuta desde `unified-mcp/`:

**Facebook:**
```bash
cd unified-mcp
python -c "
import asyncio
from pathlib import Path
from auth.facebook_auth import FacebookTokenManager

async def main():
    mgr = FacebookTokenManager(Path('.env'))
    token = await mgr.get_valid_token()
    print('OK, token activo, longitud:', len(token))

asyncio.run(main())
"
```

**Instagram:**
```bash
cd unified-mcp
python -c "
import asyncio
from pathlib import Path
from auth.instagram_auth import InstagramTokenManager

async def main():
    mgr = InstagramTokenManager(Path('.env'))
    token = await mgr.get_valid_token()
    print('OK, token activo, longitud:', len(token))

asyncio.run(main())
"
```

**Threads:**
```bash
cd unified-mcp
python -c "
import asyncio
from pathlib import Path
from auth.threads_auth import ThreadsTokenManager

async def main():
    mgr = ThreadsTokenManager(Path('.env'))
    token = await mgr.get_valid_token()
    print('OK, token activo, longitud:', len(token))

asyncio.run(main())
"
```

**LinkedIn** (solo confirma si sigue vivo; si ya caducó y no hay refresh token, lanzará `AuthError` pidiendo ejecutar el flujo manual):
```bash
cd unified-mcp
python -c "
import asyncio
from pathlib import Path
from auth.linkedin_auth import LinkedInTokenManager

async def main():
    mgr = LinkedInTokenManager(Path('.env'))
    token = await mgr.get_valid_token()
    print('OK, token activo, longitud:', len(token))

asyncio.run(main())
"
```

Si alguno de estos comandos refresca el token (Facebook/Instagram/Threads dentro de la ventana de 7 días), el nuevo valor se escribe automáticamente en `unified-mcp/.env`. Después sigue con la **sección 5** para propagarlo a Secret Manager/Cloud Run.

### 3.3 Limitación importante en Cloud Run

En Cloud Run, `persist_value()` solo actualiza la variable de entorno **en memoria del proceso en marcha** — no puede escribir de vuelta en Secret Manager. Esto significa:

- Mientras la instancia de Cloud Run siga viva, el refresco automático funciona igual que en local.
- En cuanto esa instancia se reinicia (nuevo despliegue, caída, o escala a cero tras inactividad — el servicio tiene `min-instances=0`), **vuelve a arrancar con el valor antiguo de Secret Manager**, perdiendo cualquier refresco que solo existiera en memoria.

Conclusión práctica: la renovación automática solo es "definitiva" en local. En producción (Cloud Run) siempre hay que completar el paso manual de rotar el secreto (sección 5), aunque el token en sí se haya obtenido "automáticamente".

### 3.4 (Opcional) Automatizar la comprobación periódica en Windows

Si quieres que la comprobación de la sección 3.2 se ejecute sola cada cierto tiempo (por ejemplo, cada semana, para que Facebook/Instagram/Threads se refresquen solos y solo tengas que ocuparte de LinkedIn), puedes crear una tarea programada:

```powershell
$action = New-ScheduledTaskAction -Execute "python" -Argument "-c ""import asyncio; from pathlib import Path; from auth.facebook_auth import FacebookTokenManager; asyncio.run(FacebookTokenManager(Path('unified-mcp/.env')).get_valid_token())""" -WorkingDirectory "D:\DANILO\Documents\PROYECTOS\PERSONALES\PYTHON\social-mcps\unified-mcp"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
Register-ScheduledTask -TaskName "social-mcps-refresh-facebook" -Action $action -Trigger $trigger
```

Repite para Instagram y Threads cambiando el módulo importado. Esto solo mantiene fresco el `.env` local; sigue sin sustituir la rotación en Secret Manager si usas Cloud Run (ver 3.3).

---

## 4. Renovación MANUAL (paso a paso, con comandos)

### 4.1 LinkedIn

**Accesos previos necesarios:**
- Cuenta LinkedIn con acceso a [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps).
- La app ya existe (creada previamente) con los productos **Share on LinkedIn** y **Sign In with LinkedIn using OpenID Connect** activados, y la redirect URL `https://www.linkedin.com/developers/tools/oauth/redirect` ya registrada en la pestaña **Auth**. Si algún día se crea una app nueva, hay que repetir esa configuración desde cero (ver `linkedin/README.md`, Fase 1).

**Pasos:**

1. Construye la URL de autorización (usa el `LINKEDIN_CLIENT_ID` ya guardado en `linkedin/.env` o `unified-mcp/.env`):
   ```
   https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=<LINKEDIN_CLIENT_ID>&redirect_uri=https://www.linkedin.com/developers/tools/oauth/redirect&scope=openid%20profile%20email%20w_member_social
   ```
2. Ábrela en el navegador, inicia sesión y aprueba los permisos.
3. LinkedIn te redirige a una página que muestra la URL con el `code` durante unos segundos — **copia la URL completa de la barra de direcciones** antes de que desaparezca. Tiene esta forma:
   ```
   https://www.linkedin.com/developers/tools/oauth/redirect?code=AQ...&...
   ```
4. Intercambia el código por tokens y actualiza `linkedin/.env` ejecutando el script interactivo:
   ```bash
   cd linkedin
   python oauth_setup.py
   ```
   Cuando te pida "Paste the full redirect URL...", pega la URL del paso 3.

   Alternativa no interactiva (ejecuta el intercambio directamente con el código ya copiado, sustituyendo `<URL_COMPLETA>`):
   ```bash
   cd linkedin
   python -c "
   import time
   import oauth_setup as m

   client_id = m._load_required('LINKEDIN_CLIENT_ID')
   client_secret = m._load_required('LINKEDIN_CLIENT_SECRET')
   code = m._extract_code('<URL_COMPLETA_CON_EL_CODE>')

   payload = m._exchange_code(client_id, client_secret, code)
   access_token = payload['access_token']
   refresh_token = payload.get('refresh_token', '')
   expiry = int(time.time()) + payload.get('expires_in', 5183999)
   urn = m._fetch_person_urn(access_token)

   m.set_key(str(m._ENV_PATH), 'LINKEDIN_ACCESS_TOKEN', access_token)
   m.set_key(str(m._ENV_PATH), 'LINKEDIN_REFRESH_TOKEN', refresh_token)
   m.set_key(str(m._ENV_PATH), 'LINKEDIN_TOKEN_EXPIRY', str(expiry))
   m.set_key(str(m._ENV_PATH), 'LINKEDIN_PERSON_URN', urn)
   print('Expiry:', expiry, '| URN:', urn, '| refresh_token?', bool(refresh_token))
   "
   ```
5. Comprueba que `LINKEDIN_PERSON_URN` en `linkedin/.env` tiene el formato completo `urn:li:person:XXXXXXXXXX` (si solo aparece el ID, añade el prefijo a mano).
6. Sigue con la **sección 5** para copiar los valores nuevos a `unified-mcp/.env` y rotarlos en Secret Manager.

---

### 4.2 Facebook (Page token)

**Accesos previos necesarios:**
- Ser administrador de la Facebook Page.
- App en [developers.facebook.com](https://developers.facebook.com) ya creada (tipo Business, con producto Facebook Login). Reutiliza la misma app que Instagram.

**Pasos:**

1. Ve a [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer).
2. En **Meta App**, selecciona la app del proyecto.
3. **Add a Permission** → añade: `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` (añade también `instagram_basic` e `instagram_content_publish` si vas a renovar Instagram a la vez, ver 4.3).
4. **Generate Access Token** → aprueba todos los permisos.
5. En el campo de URL de la consulta, escribe (sustituye `<slug-de-tu-pagina>`):
   ```
   /<slug-de-tu-pagina>?fields=id,name,access_token
   ```
6. Pulsa **Enviar** y copia del resultado:
   - `access_token` → `FACEBOOK_ACCESS_TOKEN`
   - `id` → `FACEBOOK_PAGE_ID`
7. Actualiza `facebook/.env` con esos valores y deja `FACEBOOK_TOKEN_EXPIRY=0` (permanente).
8. Sigue con la **sección 5**.

---

### 4.3 Instagram (Page token)

**Accesos previos necesarios:**
- Cuenta Instagram tipo **Creator** o **Business**, vinculada a la Facebook Page (Instagram → Configuración → Cuenta → Cuenta profesional → Página de Facebook vinculada).
- Misma app de Meta for Developers que Facebook.

**Pasos:**

1. Ve a [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer).
2. Selecciona la app.
3. **Add a Permission** → añade los 5: `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.
4. **Generate Access Token** → aprueba todos.
5. En el campo de URL escribe (sustituye `<slug-de-tu-pagina>`):
   ```
   /<slug-de-tu-pagina>?fields=id,instagram_business_account,access_token
   ```
6. Pulsa **Enviar** y copia:
   - `access_token` → `INSTAGRAM_ACCESS_TOKEN`
   - `instagram_business_account.id` → `INSTAGRAM_ACCOUNT_ID`
7. Actualiza `instagram/.env` y deja `INSTAGRAM_TOKEN_EXPIRY=0` (permanente).
8. Sigue con la **sección 5**.

---

### 4.4 Threads

**Accesos previos necesarios:**
- App en Meta for Developers con el producto **Threads API** habilitado y permisos `threads_basic`, `threads_content_publish`.
- Si usas el método B (`oauth_setup.py`), añade `http://localhost:8888/callback` a los redirect URIs de la app antes de ejecutar el script.

**Pasos (método recomendado — panel de Meta, sin navegador extra):**

1. Panel de la app → **Threads API** → **Genera identificadores de acceso**.
2. Copia el **identificador de acceso de larga duración** → `THREADS_ACCESS_TOKEN`.
3. Copia el **identificador de usuario** → `THREADS_USER_ID`.
4. Calcula la fecha de caducidad (60 días desde hoy) en Git Bash:
   ```bash
   echo $(($(date +%s) + 5184000))
   ```
   Ese número → `THREADS_TOKEN_EXPIRY`.
5. Actualiza `threads/.env` con los tres valores.

**Alternativa (método B, si el token ya caducó y no puedes usar el panel):**
```bash
cd threads
python oauth_setup.py
```
Abre el navegador, autoriza, intercambia el código y escribe `THREADS_ACCESS_TOKEN`, `THREADS_TOKEN_EXPIRY` y `THREADS_USER_ID` en `threads/.env` automáticamente.

Sigue con la **sección 5**.

---

### 4.5 WordPress.com

Los tokens de WordPress.com son **permanentes**. Solo hace falta repetir esto si el acceso fue revocado manualmente en [wordpress.com/me/security/connected-applications](https://wordpress.com/me/security/connected-applications).

**Accesos previos necesarios:**
- App ya creada en [developer.wordpress.com/apps](https://developer.wordpress.com/apps) con `WP_CLIENT_ID`/`WP_CLIENT_SECRET` ya guardados.

**Pasos:**

1. Ejecuta:
   ```bash
   cd wordpress
   python oauth_setup.py
   ```
2. Abre la URL que te muestra, autoriza el acceso en WordPress.com.
3. WordPress te redirige a `https://wordpress.com/?code=...` — copia esa URL completa y pégala en la terminal cuando te la pida.
4. El script lista tus sitios, seleccionas el correcto, y escribe `WP_ACCESS_TOKEN` y `WP_SITE_ID` en `wordpress/.env`.
5. Sigue con la **sección 5**.

---

### 4.6 X / Twitter (Twikit)

X no usa OAuth: el MCP inicia sesión con usuario y contraseña reales (librería Twikit, sin API oficial). No hay "token que caduque", pero puede hacer falta actualizar credenciales si:

- Cambias la contraseña de la cuenta.
- Cambias el email asociado.
- X exige verificación/challenge adicional (en ese caso puede que Twikit necesite reautenticarse manualmente la primera vez).

**Pasos:**

1. Edita `unified-mcp/.env` (o `X_USERNAME`/`X_PASSWORD`/`X_EMAIL` donde corresponda) con las credenciales nuevas.
2. Sigue con la **sección 5** para rotar `x-username`, `x-password`, `x-email` en Secret Manager si usas Cloud Run.

---

## 5. Aplicar el cambio en local + producción

Repite esto tras **cualquier** renovación manual de la sección 4 (u ocasionalmente tras una automática, ver 3.3).

### 5.1 Copiar los valores nuevos a `unified-mcp/.env`

Si renovaste desde una carpeta standalone (`linkedin/.env`, `facebook/.env`, etc.), copia las claves actualizadas a las líneas equivalentes de `unified-mcp/.env` (mismos nombres de variable).

### 5.2 Rotar los secretos en Google Secret Manager

Usa `deploy/google-cloud/rotate-secret.sh` **desde Git Bash** (nunca doble clic ni botón Run de VS Code):

```bash
cd "/d/DANILO/Documents/PROYECTOS/PERSONALES/PYTHON/social-mcps/deploy/google-cloud"
```

Rota cada secreto que haya cambiado. Nombres válidos de secreto por plataforma:

- LinkedIn: `linkedin-client-id`, `linkedin-client-secret`, `linkedin-access-token`, `linkedin-refresh-token`, `linkedin-token-expiry`, `linkedin-person-urn`
- Facebook: `facebook-app-id`, `facebook-app-secret`, `facebook-access-token`, `facebook-token-expiry`, `facebook-page-id`
- Instagram: `instagram-app-id`, `instagram-app-secret`, `instagram-access-token`, `instagram-account-id`
- Threads: `threads-app-id`, `threads-app-secret`, `threads-access-token`, `threads-user-id`
- WordPress: `wp-client-id`, `wp-client-secret`, `wp-access-token`, `wp-site-id`
- X: `x-username`, `x-password`, `x-email`

Ejemplo (rota el access token y fuerza el redeploy en el último):
```bash
bash rotate-secret.sh linkedin-access-token "<nuevo-access-token>"
bash rotate-secret.sh linkedin-token-expiry "<nuevo-timestamp>" --restart
```

El flag `--restart` solo hace falta en la **última** llamada de la tanda — fuerza que Cloud Run despliegue una revisión nueva ya mismo en vez de esperar al próximo arranque en frío.

### 5.3 Verificar que se aplicó

```bash
gcloud secrets versions list <nombre-del-secreto> --project=socialmcps --format="table(name,state,createTime)"
gcloud run services describe unified-mcp --project=socialmcps --region=europe-west1 --format="value(status.latestReadyRevisionName)"
```

La versión más reciente del secreto debe tener fecha de hoy, y la revisión de Cloud Run debe ser la que se acaba de desplegar.

---

## 6. Verificación final end-to-end

Prueba la herramienta `get_account_info` de la plataforma renovada desde el cliente MCP (Claude Desktop/Code):

- `linkedin_get_account_info`
- `facebook_get_account_info`
- `instagram_get_account_info`
- `threads_get_account_info`
- `wordpress_get_account_info`

Si responde con los datos de la cuenta sin error de autenticación (401/190), la renovación fue exitosa tanto en local como en Cloud Run.

---

## 7. Notas de seguridad

- Nunca subas ningún `.env` a Git — todos están en `.gitignore`.
- No pegues tokens ni secretos en canales públicos, issues de GitHub, ni logs compartidos.
- `MCP_AUTH_TOKEN`, `LINKEDIN_CLIENT_SECRET`, etc. son tan sensibles como una contraseña: trátalos igual.
- Si un token se filtra por error, revócalo inmediatamente desde el panel del developer correspondiente y genera uno nuevo siguiendo esta guía.
