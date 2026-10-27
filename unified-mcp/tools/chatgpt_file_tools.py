"""Import host-authorized ChatGPT attachments without routing base64 through the model."""
from __future__ import annotations

import hashlib
import io
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image
from pydantic import BaseModel, ConfigDict

from core.models import ToolResult

MAX_BYTES = 12 * 1024 * 1024
_ALLOWED_HOSTS = ('oaiusercontent.com', 'chatgpt.com', 'openai.com')


class ChatGPTFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    download_url: str
    file_id: str
    mime_type: str = ''
    file_name: str = ''


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    if parsed.scheme != 'https':
        raise ValueError('Adjunto no válido: se recibió una referencia local o un protocolo no HTTPS. ChatGPT debe proporcionar un enlace HTTPS de descarga.')
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Adjunto no válido: el enlace contiene credenciales o un puerto no admitido.')
    if not any(host == domain or host.endswith('.' + domain) for domain in _ALLOWED_HOSTS):
        # Report only the hostname: never echo the signed path, query or file ID.
        safe_host = host.encode('ascii', errors='backslashreplace').decode('ascii')[:253]
        raise ValueError('Adjunto no válido: se recibió un enlace HTTPS, pero su servidor de descarga no está admitido: ' + safe_host + '.')



async def _download_file(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as http:
        for _ in range(6):
            _validate_url(url)
            async with http.stream('GET', url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location'])
                    continue
                if response.status_code != 200:
                    raise ValueError('No se pudo descargar el adjunto de ChatGPT. Vuelve a seleccionarlo para renovar su enlace.')
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError('La imagen supera el límite de 12 MiB.')
                with Image.open(io.BytesIO(data)) as image:
                    if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 25_000_000:
                        raise ValueError('Solo se admiten imágenes JPEG, PNG o WEBP de hasta 25 megapíxeles.')
                    mime = Image.MIME[image.format]
                    image.verify()
                return bytes(data), mime
        raise ValueError('Demasiadas redirecciones al descargar el adjunto.')


async def upload_chat_image(client, file: ChatGPTFile, ttl_seconds: int = 900) -> dict:
    try:
        if not file.file_id.strip():
            raise ValueError('Falta la referencia del archivo adjunto proporcionada por ChatGPT.')
        data, mime = await _download_file(file.download_url)
        result = await client.upload_temp_image(data, mime, filename=file.file_name or None, ttl_seconds=ttl_seconds)
        result = dict(result, sha256=hashlib.sha256(data).hexdigest())
        return ToolResult(success=True, data=result).model_dump()
    except ValueError as exc:
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception:
        # Exceptions from HTTP/storage may embed signed URLs or credentials.
        return ToolResult(success=False, error='No se pudo transferir la imagen adjunta al almacenamiento temporal. Comprueba el archivo y vuelve a intentarlo.').model_dump()
