#!/usr/bin/env python3
"""
One-time OAuth 2.0 setup for the Facebook Pages API.

Prerequisites:
  - A Facebook App with the Pages API product enabled.
  - A Facebook Page you administer.
  - FACEBOOK_APP_ID and FACEBOOK_APP_SECRET already set in .env.
  - In your Facebook App settings, add this redirect URI:
      http://localhost:8888/callback

Run:
    python oauth_setup.py
"""
from __future__ import annotations

import http.server
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

_ENV_PATH = Path(__file__).parent / ".env"
_GRAPH_URL = "https://graph.facebook.com/v21.0"
_AUTH_URL = "https://www.facebook.com/v21.0/dialog/oauth"
_TOKEN_URL = f"{_GRAPH_URL}/oauth/access_token"
_REDIRECT_URI = "http://localhost:8888/callback"
_SCOPES = "pages_manage_posts,pages_read_engagement,pages_show_list"
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
        pass  # suppress server request logs


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
    response = httpx.get(
        _TOKEN_URL,
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": _REDIRECT_URI,
            "code": code,
        },
    )
    if response.status_code != 200:
        print(f"ERROR: Token exchange failed ({response.status_code}):\n{response.text}")
        sys.exit(1)
    return response.json()["access_token"]


def _exchange_long_lived(app_id: str, app_secret: str, short_token: str) -> str:
    response = httpx.get(
        _TOKEN_URL,
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
    )
    if response.status_code != 200:
        print(f"ERROR: Long-lived token exchange failed ({response.status_code}):\n{response.text}")
        sys.exit(1)
    return response.json()["access_token"]


def _get_pages(long_lived_token: str) -> list[dict]:
    response = httpx.get(
        f"{_GRAPH_URL}/me/accounts",
        params={"access_token": long_lived_token},
    )
    if response.status_code != 200:
        print(f"ERROR: Could not fetch pages ({response.status_code}):\n{response.text}")
        sys.exit(1)
    return response.json().get("data", [])


def main() -> None:
    if not _ENV_PATH.exists():
        print(f"ERROR: {_ENV_PATH} not found. Copy .env.example to .env first.")
        sys.exit(1)

    app_id = _load_required("FACEBOOK_APP_ID")
    app_secret = _load_required("FACEBOOK_APP_SECRET")

    print("\n--- Facebook Pages OAuth Setup ---")
    auth_url = _build_auth_url(app_id)
    code = _wait_for_code(auth_url)

    print("\nExchanging code for short-lived token...")
    short_token = _exchange_code(app_id, app_secret, code)

    print("Exchanging for long-lived token (60 days)...")
    long_token = _exchange_long_lived(app_id, app_secret, short_token)

    print("Fetching your Facebook Pages...")
    pages = _get_pages(long_token)
    if not pages:
        print("ERROR: No Facebook Pages found. You must be an admin of at least one Page.")
        sys.exit(1)

    if len(pages) == 1:
        page = pages[0]
        print(f"\nFound one page: {page['name']} (ID: {page['id']})")
    else:
        print("\nYour Facebook Pages:")
        for i, p in enumerate(pages):
            print(f"  [{i + 1}] {p['name']} (ID: {p['id']})")
        choice = input("Select the page to use [1]: ").strip()
        idx = int(choice) - 1 if choice.isdigit() else 0
        page = pages[idx]

    page_token = page["access_token"]

    set_key(str(_ENV_PATH), "FACEBOOK_ACCESS_TOKEN", page_token)
    set_key(str(_ENV_PATH), "FACEBOOK_TOKEN_EXPIRY", "0")
    set_key(str(_ENV_PATH), "FACEBOOK_PAGE_ID", page["id"])

    print("\n--- Setup complete ---\n")
    print(f"  Facebook Page : {page['name']} (ID: {page['id']})")
    print("  Token type    : Page Access Token (never expires)")
    print("\nYou can now start the server: python server.py\n")


if __name__ == "__main__":
    main()
