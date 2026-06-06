#!/usr/bin/env python3
"""
One-time OAuth 2.0 setup for Instagram Graph API (via Facebook Login).

Prerequisites:
  - A Facebook App with Instagram Basic Display or Graph API product enabled.
  - An Instagram Business or Creator account linked to a Facebook Page.
  - INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET already set in .env.

Steps performed:
  1. Build the Facebook Login authorization URL.
  2. User opens URL, approves scopes, gets redirected with a code.
  3. Exchange code for a short-lived User Access Token.
  4. Exchange for a Long-lived User Access Token (60 days).
  5. List Facebook Pages and let user select the correct one.
  6. Retrieve the Page Access Token (never expires).
  7. Retrieve the Instagram Business Account ID from the selected Page.
  8. Write INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_TOKEN_EXPIRY, INSTAGRAM_ACCOUNT_ID to .env.

Run:
    python oauth_setup.py
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

_ENV_PATH = Path(__file__).parent / ".env"
_GRAPH_URL = "https://graph.facebook.com/v21.0"
_AUTH_URL = "https://www.facebook.com/v21.0/dialog/oauth"
_TOKEN_URL = f"{_GRAPH_URL}/oauth/access_token"
_REDIRECT_URI = "https://www.facebook.com/connect/login_success.html"
_SCOPES = "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement"


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


def _extract_code(raw_input: str) -> str:
    raw_input = raw_input.strip()
    if raw_input.startswith("http"):
        parsed = urllib.parse.urlparse(raw_input)
        params = urllib.parse.parse_qs(parsed.query)
        codes = params.get("code", [])
        if not codes:
            print("ERROR: No 'code' parameter found in the URL.")
            sys.exit(1)
        return codes[0]
    return raw_input


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


def _exchange_long_lived(app_id: str, app_secret: str, short_token: str) -> tuple[str, int]:
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
    payload = response.json()
    import time
    expires_in = payload.get("expires_in", 5183999)
    return payload["access_token"], int(time.time()) + expires_in


def _get_pages(long_lived_token: str) -> list[dict]:
    response = httpx.get(
        f"{_GRAPH_URL}/me/accounts",
        params={"access_token": long_lived_token},
    )
    if response.status_code != 200:
        print(f"ERROR: Could not fetch pages ({response.status_code}):\n{response.text}")
        sys.exit(1)
    return response.json().get("data", [])


def _get_instagram_account_id(page_id: str, page_token: str) -> str:
    response = httpx.get(
        f"{_GRAPH_URL}/{page_id}",
        params={
            "fields": "instagram_business_account",
            "access_token": page_token,
        },
    )
    if response.status_code != 200:
        print(f"ERROR: Could not fetch Instagram account ({response.status_code}):\n{response.text}")
        sys.exit(1)
    ig_account = response.json().get("instagram_business_account")
    if not ig_account:
        print(
            "ERROR: This Facebook Page has no linked Instagram Business or Creator account.\n"
            "Go to Instagram Settings → Account → Switch to Professional Account, "
            "then link it to this Facebook Page."
        )
        sys.exit(1)
    return ig_account["id"]


def main() -> None:
    if not _ENV_PATH.exists():
        print(f"ERROR: {_ENV_PATH} not found. Copy .env.example to .env first.")
        sys.exit(1)

    app_id = _load_required("INSTAGRAM_APP_ID")
    app_secret = _load_required("INSTAGRAM_APP_SECRET")

    auth_url = _build_auth_url(app_id)
    print("\n--- Instagram OAuth Setup ---\n")
    print("1. Open this URL in your browser and authorize the application:\n")
    print(f"   {auth_url}\n")
    print("2. After approving, you will be redirected to a URL like:")
    print(f"   {_REDIRECT_URI}?code=AQT...#_=_\n")

    raw = input("3. Paste the full redirect URL or just the 'code' value:\n> ").strip()
    if not raw:
        print("ERROR: No input provided.")
        sys.exit(1)

    code = _extract_code(raw)

    print("\nExchanging code for short-lived token...")
    short_token = _exchange_code(app_id, app_secret, code)

    print("Exchanging for long-lived token (60 days)...")
    long_token, token_expiry = _exchange_long_lived(app_id, app_secret, short_token)

    print("Fetching your Facebook Pages...")
    pages = _get_pages(long_token)
    if not pages:
        print(
            "ERROR: No Facebook Pages found. Create a Facebook Page and link your "
            "Instagram Business account to it first."
        )
        sys.exit(1)

    if len(pages) == 1:
        page = pages[0]
        print(f"\nFound one page: {page['name']} (ID: {page['id']})")
    else:
        print("\nYour Facebook Pages:")
        for i, p in enumerate(pages):
            print(f"  [{i + 1}] {p['name']} (ID: {p['id']})")
        choice = input("Select the page linked to your Instagram account [1]: ").strip()
        idx = int(choice) - 1 if choice.isdigit() else 0
        page = pages[idx]

    page_token = page["access_token"]  # Page Access Token — never expires
    print(f"\nFetching Instagram Business Account from page '{page['name']}'...")
    ig_account_id = _get_instagram_account_id(page["id"], page_token)

    # Use the Page Access Token (never expires) as the stored token
    set_key(str(_ENV_PATH), "INSTAGRAM_ACCESS_TOKEN", page_token)
    set_key(str(_ENV_PATH), "INSTAGRAM_TOKEN_EXPIRY", "0")  # 0 = never expires
    set_key(str(_ENV_PATH), "INSTAGRAM_ACCOUNT_ID", ig_account_id)

    print("\n--- Setup complete ---\n")
    print(f"  Instagram Account ID : {ig_account_id}")
    print(f"  Facebook Page        : {page['name']} (ID: {page['id']})")
    print("  Token type           : Page Access Token (never expires)")
    print("\nYou can now start the server: python server.py\n")


if __name__ == "__main__":
    main()
