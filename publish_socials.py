"""
Publica el artículo de Fable 5 en LinkedIn, Facebook, Instagram, Threads y X.

Uso:
    python publish_socials.py <wordpress_url> [ruta_imagen]

Ejemplo:
    python publish_socials.py https://tusitio.wordpress.com/2026/06/13/fable5/
    python publish_socials.py https://tusitio.wordpress.com/... wordpress/fable5.jpg

- wordpress_url  : URL del artículo ya publicado en WordPress (obligatorio)
- ruta_imagen    : Ruta local al JPG descargado de Canva (opcional, para LinkedIn/Facebook)
                   Si no se pasa, intenta usar wordpress/fable5.jpg

Para Instagram se obtiene la URL pública de la imagen destacada de WordPress.
Para Threads y X no se adjunta imagen.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).parent

# ── Helpers ───────────────────────────────────────────────────────────────────

def _env(folder: str) -> dict[str, str]:
    return dotenv_values(ROOT / folder / ".env")


def _ok(label: str, detail: str = "") -> None:
    print(f"  ✅ {label}" + (f"  →  {detail}" if detail else ""))


def _warn(label: str, detail: str = "") -> None:
    print(f"  ⚠️  {label}" + (f"  →  {detail}" if detail else ""))


def _err(label: str, detail: str = "") -> None:
    print(f"  ❌ {label}" + (f"  →  {detail}" if detail else ""))


# ── Textos ────────────────────────────────────────────────────────────────────

def _texts(wp_url: str) -> dict[str, str]:
    linkedin = f"""\
El Gobierno de EE.UU. acaba de escribir un capítulo inédito en la historia de la inteligencia artificial.

El 12 de junio de 2026, el Departamento de Comercio emitió una directiva de control de exportaciones que obligó a Anthropic a desconectar Claude Fable 5 y Mythos 5 para todos sus usuarios en el mundo. El motivo: una supuesta vulnerabilidad de seguridad detectada tan solo 24 horas después del lanzamiento.

La orden, firmada por el Secretario Howard Lutnick, prohibió el acceso de cualquier nacional extranjero a los modelos, incluyendo a los propios empleados de Anthropic con ciudadanía no estadounidense. Ante la imposibilidad técnica de segmentar el acceso, Anthropic apagó los modelos para todo el mundo.

Es la primera vez en la historia que una empresa líder de IA se ve obligada a retirar un modelo ya desplegado públicamente por orden federal.

Anthropic acata la directiva pero la disputa públicamente: argumenta que la vulnerabilidad invocada es una limitación técnica compartida por todos los grandes modelos del sector. La empresa trabaja para restaurar el acceso y promete dar más detalles en las próximas 24 horas.

¿Qué precedente sienta esto para toda la industria?

📖 Artículo completo: {wp_url}

#InteligenciaArtificial #AI #Anthropic #Claude #Regulacion #Tecnologia"""

    x = (
        f"El Gobierno de EE.UU. ordenó a Anthropic apagar Fable 5 y Mythos 5 para todo el mundo. "
        f"Primera vez que una IA líder es retirada por orden federal. {wp_url}"
    )

    ig_fb = f"""\
🚨 Bombazo en el mundo de la IA

El Gobierno de EE.UU. obligó a Anthropic a apagar Claude Fable 5 y Mythos 5 en todo el mundo, \
tan solo tres días después de su lanzamiento.

La directiva prohíbe que cualquier extranjero acceda a los modelos, incluyendo a empleados de \
Anthropic con ciudadanía no estadounidense. La causa: una supuesta vulnerabilidad de seguridad \
que la propia Anthropic disputa.

Es la primera vez en la historia que una IA líder es retirada por orden del Gobierno federal de EE.UU.

🔗 Más info: {wp_url}

#IA #InteligenciaArtificial #Anthropic #Claude #FableAI #AIRegulation #Tecnologia #SeguridadNacional"""

    threads = (
        f"El Gobierno de EE.UU. ordenó a Anthropic apagar Fable 5 y Mythos 5 solo 3 días después "
        f"del lanzamiento. La primera IA líder retirada por orden federal de la historia. 👉 {wp_url}"
    )

    return {"linkedin": linkedin, "x": x, "ig_fb": ig_fb, "threads": threads}


# ── WordPress: obtener URL de imagen destacada ─────────────────────────────────

async def _get_wp_featured_image_url(wp_post_url: str) -> str | None:
    """Intenta obtener la URL pública de la imagen destacada del post de WordPress."""
    try:
        env = _env("wordpress")
        token = env["WP_ACCESS_TOKEN"]
        site_id = env["WP_SITE_ID"]
        async with httpx.AsyncClient(timeout=20) as client:
            # Buscar el post por URL
            r = await client.get(
                f"https://public-api.wordpress.com/rest/v1.1/sites/{site_id}/posts",
                headers={"Authorization": f"Bearer {token}"},
                params={"search": wp_post_url.split("/")[-2], "number": 5},
            )
            posts = r.json().get("posts", [])
            for post in posts:
                if post.get("URL") == wp_post_url or wp_post_url in post.get("URL", ""):
                    featured = post.get("featured_image")
                    if featured:
                        return featured
    except Exception as exc:
        _warn(f"No se pudo obtener imagen destacada de WordPress: {exc}")
    return None


# ── LinkedIn ──────────────────────────────────────────────────────────────────

async def publish_linkedin(text: str, image_path: Path | None) -> None:
    print("\n🔵 LinkedIn...")
    try:
        env = _env("linkedin")
        token = env["LINKEDIN_ACCESS_TOKEN"]
        person_urn = env["LINKEDIN_PERSON_URN"]
        expiry = int(env.get("LINKEDIN_TOKEN_EXPIRY", 0))
        if expiry and int(time.time()) >= expiry:
            _warn("Token de LinkedIn expirado — ejecuta linkedin/oauth_setup.py")
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "LinkedIn-Version": "202401",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

        asset_urn: str | None = None
        if image_path and image_path.exists():
            # 1. Registrar upload
            async with httpx.AsyncClient(base_url="https://api.linkedin.com", timeout=30) as c:
                r = await c.post(
                    "/v2/assets",
                    params={"action": "registerUpload"},
                    json={
                        "registerUploadRequest": {
                            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                            "owner": person_urn,
                            "serviceRelationships": [
                                {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
                            ],
                        }
                    },
                    headers=headers,
                )
                r.raise_for_status()
                value = r.json()["value"]
                upload_url = value["uploadMechanism"][
                    "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
                ]["uploadUrl"]
                asset_urn = value["asset"]

            # 2. Subir imagen
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.put(upload_url, content=image_path.read_bytes(),
                                headers={"Content-Type": "application/octet-stream"})
                r.raise_for_status()

        # 3. Crear post
        share_content: dict = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "IMAGE" if asset_urn else "NONE",
        }
        if asset_urn:
            share_content["media"] = [{"status": "READY", "media": asset_urn}]

        async with httpx.AsyncClient(base_url="https://api.linkedin.com", timeout=30) as c:
            r = await c.post(
                "/v2/ugcPosts",
                json={
                    "author": person_urn,
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
                    "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
                },
                headers=headers,
            )
            r.raise_for_status()
            post_id = r.headers.get("x-restli-id", "—")
        _ok("LinkedIn publicado", post_id)
    except Exception as exc:
        _err("LinkedIn", str(exc))


# ── Facebook ──────────────────────────────────────────────────────────────────

async def publish_facebook(text: str, image_path: Path | None) -> None:
    print("\n📘 Facebook...")
    try:
        env = _env("facebook")
        token = env["FACEBOOK_ACCESS_TOKEN"]
        page_id = env["FACEBOOK_PAGE_ID"]
        base = f"https://graph.facebook.com/v21.0/{page_id}"

        async with httpx.AsyncClient(timeout=60) as c:
            if image_path and image_path.exists():
                image_bytes = image_path.read_bytes()
                r = await c.post(
                    f"{base}/photos",
                    params={"access_token": token},
                    data={"caption": text},
                    files={"source": ("fable5.jpg", image_bytes, "image/jpeg")},
                )
            else:
                r = await c.post(f"{base}/feed", params={"access_token": token},
                                 json={"message": text})

        if r.status_code == 200:
            post_id = r.json().get("post_id") or r.json().get("id", "—")
            _ok("Facebook publicado", post_id)
        else:
            # Facebook a veces devuelve error vacío aunque publica
            _warn("Facebook: verificar manualmente (posible éxito)", r.text[:100])
    except Exception as exc:
        _err("Facebook", str(exc))


# ── Instagram ─────────────────────────────────────────────────────────────────

async def publish_instagram(caption: str, image_url: str | None) -> None:
    print("\n📸 Instagram...")
    if not image_url:
        _warn("Instagram: sin URL pública de imagen, se omite")
        print("       Publica manualmente desde el dashboard o pasa la URL de la imagen WP.")
        return
    try:
        env = _env("instagram")
        token = env["INSTAGRAM_ACCESS_TOKEN"]
        account_id = env["INSTAGRAM_ACCOUNT_ID"]
        base = f"https://graph.facebook.com/v21.0/{account_id}"

        async with httpx.AsyncClient(timeout=60) as c:
            # Crear contenedor
            r = await c.post(f"{base}/media", params={"access_token": token},
                             json={"image_url": image_url, "caption": caption})
            r.raise_for_status()
            container_id = r.json()["id"]

            # Esperar a que esté listo
            for _ in range(15):
                await asyncio.sleep(4)
                r2 = await c.get(f"https://graph.facebook.com/v21.0/{container_id}",
                                 params={"fields": "status_code", "access_token": token})
                if r2.json().get("status_code") == "FINISHED":
                    break

            # Publicar
            r3 = await c.post(f"{base}/media_publish", params={"access_token": token},
                              json={"creation_id": container_id})
            r3.raise_for_status()
        _ok("Instagram publicado", r3.json().get("id", "—"))
    except Exception as exc:
        _err("Instagram", str(exc))


# ── Threads ───────────────────────────────────────────────────────────────────

async def publish_threads(text: str) -> None:
    print("\n🧵 Threads...")
    try:
        env = _env("threads")
        token = env["THREADS_ACCESS_TOKEN"]
        user_id = env["THREADS_USER_ID"]
        base = f"https://graph.threads.net/v1.0/{user_id}"

        async with httpx.AsyncClient(timeout=30) as c:
            # Crear contenedor
            r = await c.post(f"{base}/threads",
                             params={"access_token": token, "media_type": "TEXT", "text": text})
            r.raise_for_status()
            container_id = r.json()["id"]

            # Esperar
            for _ in range(10):
                await asyncio.sleep(3)
                r2 = await c.get(f"https://graph.threads.net/v1.0/{container_id}",
                                 params={"fields": "status", "access_token": token})
                if r2.json().get("status") in ("FINISHED", None):
                    break

            # Publicar
            r3 = await c.post(f"{base}/threads_publish",
                              params={"access_token": token, "creation_id": container_id})
            r3.raise_for_status()
        _ok("Threads publicado", r3.json().get("id", "—"))
    except Exception as exc:
        _err("Threads", str(exc))


# ── X (via social-automation-mcp Node.js) ────────────────────────────────────

def publish_x(text: str) -> None:
    print("\n🐦 X...")
    mcp_dir = ROOT / "social-automation-mcp"
    build_file = mcp_dir / "build" / "tools" / "post-to-x.js"

    if not build_file.exists():
        _warn("X: social-automation-mcp no compilado. Ejecuta: cd social-automation-mcp && npm run build")
        print(f"\n       Texto para copiar manualmente en x.com/compose/post:")
        print(f"       {text}")
        return

    try:
        script = f"""
const {{ postToX }} = require({str(build_file)!r});
postToX({text!r}).then(r => {{ console.log(JSON.stringify(r)); process.exit(r.success ? 0 : 1); }});
"""
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
        data = {}
        for line in result.stdout.splitlines():
            if line.startswith("{"):
                import json
                data = json.loads(line)
                break
        if data.get("success"):
            _ok("X publicado", data.get("url", "—"))
        else:
            _warn("X — verificar manualmente", data.get("error", result.stderr[:100]))
            print(f"\n       Texto: {text}")
    except Exception as exc:
        _err("X", str(exc))
        print(f"\n       Texto para copiar: {text}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python publish_socials.py <wordpress_url> [ruta_imagen]")
        sys.exit(1)

    wp_url = sys.argv[1].strip()
    image_arg = Path(sys.argv[2]) if len(sys.argv) >= 3 else ROOT / "wordpress" / "fable5.jpg"
    image_path = image_arg if image_arg.exists() else None

    if image_path:
        print(f"Imagen local: {image_path}")
    else:
        print("Sin imagen local (LinkedIn/Facebook publicarán solo texto).")

    print(f"WordPress URL: {wp_url}")
    print("Obteniendo URL de imagen destacada para Instagram...")
    ig_image_url = await _get_wp_featured_image_url(wp_url)
    if ig_image_url:
        print(f"  Imagen WP: {ig_image_url}")
    else:
        print("  No encontrada — Instagram se saltará.")

    texts = _texts(wp_url)

    await publish_linkedin(texts["linkedin"], image_path)
    await publish_facebook(texts["ig_fb"], image_path)
    await publish_instagram(texts["ig_fb"], ig_image_url)
    await publish_threads(texts["threads"])
    publish_x(texts["x"])

    print("\n\n📤 Publicación completada")
    print(f"{'Canal':<12} {'Resultado'}")
    print("-" * 40)
    print("Revisa los ✅/⚠️/❌ de arriba para cada canal.")


if __name__ == "__main__":
    asyncio.run(main())
