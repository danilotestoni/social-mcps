#!/usr/bin/env python3
"""
One-time OAuth 2.0 setup for the Threads API.

Prerequisites:
  - A Threads app in Meta for Developers with threads_basic and threads_content_publish.
  - THREADS_APP_ID and THREADS_APP_SECRET already set in .env.
  - In your app settings, add this redirect URI:
      http://localhost:8888/callback

Run:
    python oauth_setup.py
"""
from __future__ import annotations

import http.server
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

_ENV_PATH = Path(__file__).parent / ".env"
_AUTH_URL = "https://threads.net/oauth/authorize"
_TOKEN_URL = "https://graph.threads.net/oauth/access_token"
_LONG_LIVED_URL = "https://graph.threads.net/access_token"
_THREADS_URL = "https://graph.threads.net/v1.0"
_REDIRECT_URI = "http://localhost:8888/callback"
_SCOPES = "threads_basic,threads_content_publish"
_PORT = 8888


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    captured_code: str | None = None
    captured_error: str | None = None

    def do_GET(self) -> None:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            _CallbackHandler.captured_code = params["code"][0]
            body = b"<html><body><h2>Autorizado correctamente. Puedes cerrar esta ventana.</h2></body></html>"
        else:
            _CallbackHandler.captured_error = params.get("error_description", ["Error desconocido"])[0]
            body = b"<html><body><h2>Error de autorizacion. Vuelve a la terminal.</h2></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _wait_for_code(auth_url: str) -> str:
    server = http.server.HTTPServer(("localhost", _PORT), _CallbackHandler)
    print(f"\nAbriendo el navegador para autorizar la aplicación...")
    webbrowser.open(auth_url)
    print("Si el navegador no se abre, copia esta URL manualmente:\n")
    print(f"  {auth_url}\n")
    print("Esperando autorización en el navegador...")
    server.handle_request()
    if _CallbackHandler.captured_error:
        print(f"ERROR: {_CallbackHandler.captured_error}")
        sys.exit(1)
    if not _CallbackHandler.captured_code:
        print("ERROR: No se recibió el código de autorización.")
        sys.exit(1)
    return _CallbackHandler.captured_code


def _load_required(key: str) -> str:
    values = dotenv_values(_ENV_PATH)
    value = values.get(key, "").strip()
    if not value:
        print(f"ERROR: {key} is missing or empty in {_ENV_PATH}")
        sys.exit(1)
    return value


def _build_auth_url(app_id: str) -> str:
    params = urllib.parse.urlencode(
        {
            "client_id": app_id,
            "redirect_uri": _REDIRECT_URI,
            "scope": _SCOPES,
            "response_type": "code",
        }
    )
    return f"{_AUTH_URL}?{params}"


def _exchange_code(app_id: str, app_secret: str, code: str) -> str:
    response = httpx.post(
        _TOKEN_URL,
        data={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": _REDIRECT_URI,
            "code": code,
            "grant_type": "authorization_code",
        },
    )
    if response.status_code != 200:
        print(f"ERROR: Token exchange failed ({response.status_code}):\n{response.text}")
        sys.exit(1)
    return response.json()["access_token"]


def _exchange_long_lived(app_id: str, app_secret: str, short_token: str) -> tuple[str, int]:
    response = httpx.get(
        _LONG_LIVED_URL,
        params={
            "grant_type": "th_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "access_token": short_token,
        },
    )
    if response.status_code != 200:
        print(f"ERROR: Long-lived token exchange failed ({response.status_code}):\n{response.text}")
        sys.exit(1)
    payload = response.json()
    expires_in = payload.get("expires_in", 5183999)
    return payload["access_token"], int(time.time()) + expires_in


def _get_user_id(token: str) -> tuple[str, str]:
    response = httpx.get(
        f"{_THREADS_URL}/me",
        params={"fields": "id,username", "access_token": token},
    )
    if response.status_code != 200:
        print(f"ERROR: Could not fetch user info ({response.status_code}):\n{response.text}")
        sys.exit(1)
    data = response.json()
    return data["id"], data.get("username", "")


def main() -> None:
    if not _ENV_PATH.exists():
        print(f"ERROR: {_ENV_PATH} not found. Copy .env.example to .env first.")
        sys.exit(1)

    app_id = _load_required("THREADS_APP_ID")
    app_secret = _load_required("THREADS_APP_SECRET")

    print("\n--- Threads OAuth Setup ---")
    auth_url = _build_auth_url(app_id)
    code = _wait_for_code(auth_url)

    print("\nExchanging code for short-lived token...")
    short_token = _exchange_code(app_id, app_secret, code)

    print("Exchanging for long-lived token (60 days)...")
    long_token, token_expiry = _exchange_long_lived(app_id, app_secret, short_token)

    print("Fetching Threads user info...")
    user_id, username = _get_user_id(long_token)

    set_key(str(_ENV_PATH), "THREADS_ACCESS_TOKEN", long_token)
    set_key(str(_ENV_PATH), "THREADS_TOKEN_EXPIRY", str(token_expiry))
    set_key(str(_ENV_PATH), "THREADS_USER_ID", user_id)

    print("\n--- Setup complete ---\n")
    print(f"  Threads User : @{username} (ID: {user_id})")
    print(f"  Token expiry : {token_expiry} (~60 days, auto-renovable)")
    print("\nYou can now start the server: python server.py\n")


if __name__ == "__main__":
    main()
