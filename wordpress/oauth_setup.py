#!/usr/bin/env python3
"""
One-time OAuth 2.0 setup for the WordPress.com REST API.

Prerequisites:
  - A WordPress.com application registered at https://developer.wordpress.com/apps/
  - WP_CLIENT_ID and WP_CLIENT_SECRET already set in .env.
  - The app's redirect URL must be set to: https://wordpress.com/

Steps performed:
  1. Build the WordPress.com authorization URL.
  2. User opens URL in browser, approves, gets redirected with a code.
  3. Exchange code for a permanent access token.
  4. List user's WordPress.com sites and let user select the correct one.
  5. Write WP_ACCESS_TOKEN and WP_SITE_ID to .env.

Note: WordPress.com access tokens do not expire. They remain valid until
manually revoked at https://wordpress.com/me/security/connected-applications

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
_AUTH_URL = "https://public-api.wordpress.com/oauth2/authorize"
_TOKEN_URL = "https://public-api.wordpress.com/oauth2/token"
_API_BASE = "https://public-api.wordpress.com/rest/v1.1"
_REDIRECT_URI = "https://wordpress.com/"


def _load_required(key: str) -> str:
    values = dotenv_values(_ENV_PATH)
    value = values.get(key, "").strip()
    if not value:
        print(f"ERROR: {key} is missing or empty in {_ENV_PATH}")
        sys.exit(1)
    return value


def _build_auth_url(client_id: str) -> str:
    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": _REDIRECT_URI,
            "response_type": "code",
            "scope": "global",
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


def _exchange_code(client_id: str, client_secret: str, code: str) -> str:
    response = httpx.post(
        _TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": _REDIRECT_URI,
            "code": code,
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        print(f"ERROR: Token exchange failed ({response.status_code}):\n{response.text}")
        sys.exit(1)
    return response.json()["access_token"]


def _get_sites(access_token: str) -> list[dict]:
    response = httpx.get(
        f"{_API_BASE}/me/sites",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "ID,name,URL"},
    )
    if response.status_code != 200:
        print(f"ERROR: Could not fetch sites ({response.status_code}):\n{response.text}")
        sys.exit(1)
    return response.json().get("sites", [])


def main() -> None:
    if not _ENV_PATH.exists():
        print(f"ERROR: {_ENV_PATH} not found. Copy .env.example to .env first.")
        sys.exit(1)

    client_id = _load_required("WP_CLIENT_ID")
    client_secret = _load_required("WP_CLIENT_SECRET")

    auth_url = _build_auth_url(client_id)
    print("\n--- WordPress.com OAuth Setup ---\n")
    print("1. Open this URL in your browser and authorize the application:\n")
    print(f"   {auth_url}\n")
    print("2. After approving, you will be redirected to wordpress.com")
    print("   The URL will contain a 'code' parameter like:")
    print("   https://wordpress.com/?code=abc123...\n")

    raw = input("3. Paste the full redirect URL or just the 'code' value:\n> ").strip()
    if not raw:
        print("ERROR: No input provided.")
        sys.exit(1)

    code = _extract_code(raw)

    print("\nExchanging code for access token...")
    access_token = _exchange_code(client_id, client_secret, code)

    print("Fetching your WordPress.com sites...")
    sites = _get_sites(access_token)
    if not sites:
        print("ERROR: No WordPress.com sites found for this account.")
        sys.exit(1)

    if len(sites) == 1:
        site = sites[0]
        print(f"\nFound one site: {site['name']} ({site['URL']})")
    else:
        print("\nYour WordPress.com sites:")
        for i, s in enumerate(sites):
            print(f"  [{i + 1}] {s['name']} — {s['URL']} (ID: {s['ID']})")
        choice = input("Select the site to use [1]: ").strip()
        idx = int(choice) - 1 if choice.isdigit() else 0
        site = sites[idx]

    set_key(str(_ENV_PATH), "WP_ACCESS_TOKEN", access_token)
    set_key(str(_ENV_PATH), "WP_SITE_ID", str(site["ID"]))

    print("\n--- Setup complete ---\n")
    print(f"  Site  : {site['name']} ({site['URL']})")
    print(f"  ID    : {site['ID']}")
    print("  Token : permanent (no expiry)")
    print(
        "\nTo revoke access anytime, visit: "
        "https://wordpress.com/me/security/connected-applications"
    )
    print("\nYou can now start the server: python server.py\n")


if __name__ == "__main__":
    main()
