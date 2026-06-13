"""
Publica el artículo sobre el bloqueo de Fable 5 en WordPress.com.
Ejecutar desde la carpeta wordpress/ del proyecto:

    python publish_fable5.py

La imagen se descarga automáticamente de Canva. Si la URL ha expirado,
coloca manualmente el JPG en la misma carpeta con el nombre fable5.jpg
y vuelve a ejecutar.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

# ── Credenciales ─────────────────────────────────────────────────────────────
_ENV = dotenv_values(Path(__file__).parent / ".env")
TOKEN   = _ENV["WP_ACCESS_TOKEN"]
SITE_ID = _ENV["WP_SITE_ID"]
BASE    = f"https://public-api.wordpress.com/rest/v1.1/sites/{SITE_ID}"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# URL de exportación de Canva (válida ~80 min desde las 18:11 UTC del 13-jun-2026)
CANVA_URL = (
    "https://export-download.canva.com/hlc2g/DAHMeVhlc2g/-1/0/"
    "0001-5588347537135128263.jpg"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256"
    "&X-Amz-Credential=AKIAQYCGKMUH5AO7UJ26%2F20260613%2Fus-east-1%2Fs3%2Faws4_request"
    "&X-Amz-Date=20260613T105240Z"
    "&X-Amz-Expires=31148"
    "&X-Amz-Signature=6037d8a04e150bd88199d3d738c209bc8a624f2c71a9c23d8a97a50759179a1b"
    "&X-Amz-SignedHeaders=host%3Bx-amz-expected-bucket-owner"
    "&response-expires=Sat%2C%2013%20Jun%202026%2019%3A31%3A48%20GMT"
)
LOCAL_IMAGE = Path(__file__).parent / "fable5.jpg"

# ── Contenido del artículo ────────────────────────────────────────────────────
TITLE = "Mi gozo en un pozo: el Gobierno de EE.UU. apaga Claude Fable 5 de un plumazo"

CONTENT = """\
<p><strong>Tres días. Solo tres días duró la fiesta.</strong> El 9 de junio de 2026, \
Anthropic presentó al mundo lo que sin duda era su obra más ambiciosa hasta la fecha: \
Claude Fable 5 y Claude Mythos 5, dos modelos de inteligencia artificial que marcaban \
un antes y un después en el sector. Para quienes llevábamos meses esperando ese \
lanzamiento, fue como abrir el mejor regalo posible. Y entonces llegó el Gobierno de \
los Estados Unidos y se lo llevó todo de vuelta.</p>

<h3>Bombazo en el mundo de la IA</h3>

<p>El viernes 12 de junio de 2026, a las 5:21 de la tarde (hora de la costa Este), \
Anthropic recibió una directiva oficial que nadie esperaba. Firmada por <strong>Howard \
Lutnick, Secretario de Comercio</strong>, y elaborada con la colaboración de la \
<strong>Oficina de Industria y Seguridad (BIS)</strong> del Departamento de Comercio, \
la orden era taxativa: suspensión inmediata del acceso a Fable 5 y Mythos 5 para \
cualquier nacional extranjero, independientemente de si se encontraba dentro o fuera \
del territorio estadounidense. Y aquí viene el matiz que lo hace todavía más \
surrealista: <strong>los propios empleados de Anthropic con ciudadanía no estadounidense \
quedaban también excluidos</strong>.</p>

<p>La orden invocaba autoridades de seguridad nacional y control de exportaciones. \
Anthropic no tenía margen técnico para bloquear solo a los extranjeros sin tumbar los \
modelos para todo el mundo. Así que tomó la única decisión posible: <strong>desconectar \
Fable 5 y Mythos 5 para la totalidad de sus clientes en el planeta</strong>. Empresas, \
desarrolladores, usuarios particulares... todos a la calle.</p>

<p>Estamos ante un hito histórico: <strong>es la primera vez que una empresa líder en \
inteligencia artificial se ve obligada a retirar un modelo ya desplegado públicamente \
por orden del Gobierno federal de Estados Unidos.</strong></p>

<h3>¿Qué detonó todo esto? Un "jailbreak" que encendió Washington</h3>

<p>El 10 de junio, apenas 24 horas después del lanzamiento, el conocido investigador de \
seguridad que opera en X bajo el alias <strong>"Pliny the Liberator"</strong> publicó un \
mensaje que se hizo viral en cuestión de minutos: <em>"JAILBREAK ALERT, ANTHROPIC PWNED, \
FABLE 5 LIBERATED"</em>.</p>

<p>Según su relato, había logrado burlar los sistemas de seguridad del modelo usando una \
combinación de técnicas: manipulación de caracteres Unicode, prompts de contexto \
extremadamente largo, descomposición narrativa y ataques de multi-agente que fragmentan \
peticiones complejas en instrucciones aparentemente inocuas. El resultado que afirmaba \
haber obtenido: instrucciones funcionales para exploits de ciberseguridad, síntesis de \
explosivos y rutas de síntesis química. También filtró el prompt de sistema del modelo, \
de <strong>120.000 caracteres</strong>.</p>

<p>Lo que realmente prendió la mecha en Washington fue que <strong>otra empresa afirmó \
haber replicado el ataque sobre Mythos 5</strong> y lo comunicó directamente al Gobierno. \
La administración entró en pánico.</p>

<p>Anthropic, sin embargo, disputa la gravedad del asunto. En su comunicado oficial, la \
empresa señala que el método descrito se basa en <strong>limitaciones técnicas \
compartidas por prácticamente todos los grandes modelos de lenguaje del sector</strong>, \
y que si este criterio se aplicara como estándar, equivaldría en la práctica a paralizar \
el despliegue de todos los modelos de frontera de la industria.</p>

<h3>Anthropic acata, pero no se calla</h3>

<p>En su <a href="https://www.anthropic.com/news/fable-mythos-access">comunicado \
oficial</a>, Anthropic dejó claro su posición: <strong>cumple con la directiva, pero no \
está de acuerdo con ella</strong>. La empresa califica la situación de "malentendido" y \
trabaja con urgencia para restaurar el acceso. El resto de modelos (Opus 4.8, Sonnet y \
Haiku) permanecen disponibles con normalidad.</p>

<h3>El contexto: una pelea que viene de lejos</h3>

<p>Este episodio no surge de la nada. En <strong>febrero de 2026</strong>, el Pentágono \
amenazó con cancelar su contrato de <strong>200 millones de dólares</strong> con \
Anthropic si la empresa no eliminaba las restricciones sobre el uso de su IA para fines \
militares y de vigilancia. Anthropic se negó, fue declarada <strong>"riesgo en la cadena \
de suministro"</strong> por el Departamento de Defensa, y acabó presentando una demanda \
alegando vulneración de la libertad de expresión. Un juez federal en California falló a \
favor de Anthropic con una medida cautelar. El Departamento de Justicia apeló esa \
decisión.</p>

<p>El <strong>2 de junio de 2026</strong>, apenas diez días antes del bloqueo, Trump \
firmó una orden ejecutiva sobre IA que diseñaba un mecanismo para que el Gobierno tuviera \
<strong>acceso anticipado a los modelos más potentes</strong> de empresas como Anthropic \
y OpenAI. A la luz de lo ocurrido, esa orden adquiere un significado diferente.</p>

<p>Desde el Congreso, la representante <strong>Zoe Lofgren</strong> expresó su \
consternación ante lo que describió como los ataques de la administración a Anthropic, \
advirtiendo sobre las consecuencias para la competitividad tecnológica de Estados \
Unidos.</p>

<h3>Estado actual: los modelos siguen apagados</h3>

<p>A la hora de publicar este artículo, <strong>Fable 5 y Mythos 5 continúan sin estar \
disponibles</strong>. Quedan muchas preguntas abiertas sobre el alcance real de esta \
directiva y sus implicaciones para toda la industria, preguntas que esperamos vean \
respuesta en las próximas 24 horas, tal y como ha prometido Anthropic.</p>

<p><strong>El bombazo ha explotado. Las réplicas están por llegar.</strong></p>

<hr>

<p><small><strong>Fuentes:</strong> \
<a href="https://www.anthropic.com/news/fable-mythos-access">Anthropic</a> &middot; \
<a href="https://www.cnbc.com/2026/06/12/anthropic-disables-access-to-fable-5-and-mythos-5-to-comply-with-government-directive.html">CNBC</a> &middot; \
<a href="https://www.axios.com/2026/06/12/anthropic-trump-mythos-fable-national-security">Axios</a> &middot; \
<a href="https://www.bloomberg.com/news/articles/2026-06-13/anthropic-says-us-limits-foreign-access-to-fable-5-mythos-5">Bloomberg</a> &middot; \
<a href="https://www.nbcnews.com/tech/tech-news/anthropic-suspends-new-ai-models-fable-mythos-government-directive-rcna349901">NBC News</a> &middot; \
<a href="https://fortune.com/2026/06/13/anthropic-disables-fable-mythos-export-controls-national-security-threat/">Fortune</a> &middot; \
<a href="https://techcrunch.com/2026/06/12/anthropics-safety-warnings-may-have-just-backfired-the-government-has-pulled-the-plug-on-its-most-powerful-ai/">TechCrunch</a> &middot; \
<a href="https://www.securityweek.com/anthropic-disputes-fable-5-ai-jailbreak/">SecurityWeek</a>\
</small></p>"""


def get_image() -> Path | None:
    if LOCAL_IMAGE.exists():
        print(f"Usando imagen local: {LOCAL_IMAGE}")
        return LOCAL_IMAGE
    print("Descargando imagen de Canva...")
    try:
        r = httpx.get(CANVA_URL, follow_redirects=True, timeout=30)
        r.raise_for_status()
        LOCAL_IMAGE.write_bytes(r.content)
        print(f"  OK ({len(r.content) // 1024} KB) → {LOCAL_IMAGE}")
        return LOCAL_IMAGE
    except Exception as exc:
        print(f"  No se pudo descargar ({exc}).")
        print("  Coloca la imagen manualmente como fable5.jpg en esta carpeta y ejecuta de nuevo.")
        return None


def upload_media(image_path: Path) -> int:
    print("Subiendo imagen a WordPress...")
    with image_path.open("rb") as fh:
        r = httpx.post(
            f"{BASE}/media/new",
            headers=HEADERS,
            files={"media[]": ("fable5-blocked.jpg", fh, "image/jpeg")},
            timeout=60,
        )
    r.raise_for_status()
    media_id = r.json()["media"][0]["ID"]
    print(f"  Media ID: {media_id}")
    return media_id


def publish(media_id: int | None) -> dict:
    print("Publicando artículo...")
    data: dict = {
        "title": TITLE,
        "content": CONTENT,
        "status": "publish",
        "format": "standard",
    }
    if media_id:
        data["featured_image"] = str(media_id)
    r = httpx.post(
        f"{BASE}/posts/new",
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def main() -> None:
    image_path = get_image()
    media_id = upload_media(image_path) if image_path else None
    if not media_id:
        print("  Publicando sin imagen destacada (puedes añadirla desde el dashboard).")
    post = publish(media_id)
    print("\n¡Publicado!")
    print(f"  Post ID : {post['ID']}")
    print(f"  URL     : {post['URL']}")
    print(f"  Short   : {post.get('short_URL', '-')}")


if __name__ == "__main__":
    main()
