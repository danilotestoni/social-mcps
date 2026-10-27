from __future__ import annotations
import asyncio
import hashlib
import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.chatgpt_file_tools import ChatGPTFile, upload_chat_image


def image_bytes():
    out = io.BytesIO()
    Image.new('RGB', (20, 12), 'blue').save(out, 'PNG')
    return out.getvalue()


def run_upload(handler, url='https://files.oaiusercontent.com/image?token=private'):
    client = AsyncMock()
    client.upload_temp_image.return_value = {'public_url':'https://public.example/temp-image/token'}
    factory = httpx.AsyncClient
    with patch('tools.chatgpt_file_tools.httpx.AsyncClient', side_effect=lambda **kw: factory(transport=httpx.MockTransport(handler), **kw)):
        result = asyncio.run(upload_chat_image(client, ChatGPTFile(download_url=url, file_id='file_test')))
    return result, client


def test_uploaded_file_preserves_original_bytes_and_hash():
    raw = image_bytes()
    result, client = run_upload(lambda req: httpx.Response(200, content=raw))
    assert result['success'] is True
    client.upload_temp_image.assert_awaited_once_with(raw, 'image/png', filename=None, ttl_seconds=900)
    assert result['data']['sha256'] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('url', ['/mnt/data/image.png','sandbox:/mnt/data/image.png','https://evil.example/i','https://files.oaiusercontent.com.evil.example/i','https://files.oaiusercontent.com@127.0.0.1/i'])
def test_untrusted_file_url_never_requested(url):
    def no_request(req):
        pytest.fail('Untrusted URL was requested')
    result, client = run_upload(no_request, url)
    assert result['success'] is False
    client.upload_temp_image.assert_not_awaited()


def test_redirect_to_untrusted_host_blocked():
    requests=[]
    def handler(req):
        requests.append(req)
        return httpx.Response(302, headers={'location':'https://evil.example/i'})
    result, client = run_upload(handler)
    assert result['success'] is False and len(requests)==1
    client.upload_temp_image.assert_not_awaited()


@pytest.mark.parametrize('response', [httpx.Response(403), httpx.Response(200,content=b'not an image')])
def test_download_failure_does_not_store_or_leak_signed_url(response):
    result, client = run_upload(lambda req: response)
    assert result['success'] is False
    assert 'private' not in result['error'] and 'token=' not in result['error']
    client.upload_temp_image.assert_not_awaited()


def test_oversized_download_rejected(monkeypatch):
    monkeypatch.setattr('tools.chatgpt_file_tools.MAX_BYTES', 10)
    result, client = run_upload(lambda req: httpx.Response(200,content=image_bytes()))
    assert result['success'] is False
    client.upload_temp_image.assert_not_awaited()


def test_file_schema_matches_host_contract():
    schema=ChatGPTFile.model_json_schema()
    assert set(schema['required'])=={'download_url','file_id'}
    assert set(schema['properties'])=={'download_url','file_id','mime_type','file_name'}
    assert schema['properties']['mime_type']['type']=='string'
    assert schema['properties']['file_name']['type']=='string'
