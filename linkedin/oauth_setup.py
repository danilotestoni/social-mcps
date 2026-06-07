#!/usr/bin/env python3
"""
One-time OAuth 2.0 authorization flow for LinkedIn.

Run this script once to obtain access and refresh tokens:
    1. Fill LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in your .env file.
    2. Run: python oauth_setup.py
    3. Open the printed URL in a browser and authorize the app.
    4. Paste the full redirect URL (or just the `code` query parameter) when prompted.
    5. Tokens and your person URN are written to .env automatically.
"""
from __future__ import annotations

import sys
import time
import urllib.parse
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

_ENV_PATH = Path(__file__).parent / ".env"
_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
_SCOPES = "openid profile email w_member_social"
_REDIRECT_URI = "https://www.linkedin.com/developers/tools/oauth/redirect"


def _load_required(key: str) -> str:
    values = dotenv_values(_ENV_PATH)
    value = values.get(key, "").strip()
    if not value:
        print(f"ERROR: {key} is missing or empty in {_ENV_PATH}")
        print("Please set it before running this script.")
        sys.exit(1)
    return value


def _build_auth_url(client_id: str) -> str:
    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": _REDIRECT_URI,
            "scope": _SCOPES,
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


def _exchange_code(client_id: str, client_secret: str, code: str) -> dict:
    response = httpx.post(
        _TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT_URI,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        print(f"ERROR: Token exchange failed ({response.status_code}):")
        print(response.text)
        sys.exit(1)
    return response.json()


def _fetch_person_urn(access_token: str) -> str:
    # OpenID Connect userinfo endpoint — works with the 'profile' scope
    response = httpx.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        print(f"ERROR: Could not fetch profile ({response.status_code}):")
        print(response.text)
        sys.exit(1)
    # 'sub' is the full person URN: urn:li:person:xxxx
    return response.json()["sub"]


def main() -> None:
    if not _ENV_PATH.exists():
        print(f"ERROR: {_ENV_PATH} not found.")
        print(f"Copy .env.example to .env and fill in CLIENT_ID and CLIENT_SECRET first.")
        sys.exit(1)

    client_id = _load_required("LINKEDIN_CLIENT_ID")
    client_secret = _load_required("LINKEDIN_CLIENT_SECRET")

    auth_url = _build_auth_url(client_id)
    print("\n--- LinkedIn OAuth Setup ---\n")
    print("1. Open this URL in your browser and authorize the application:\n")
    print(f"   {auth_url}\n")
    print("2. After approving, you will be redirected to a URL like:")
    print(f"   {_REDIRECT_URI}?code=AQT...&state=...\n")

    raw = input("3. Paste the full redirect URL or just the 'code' value here:\n> ").strip()
    if not raw:
        print("ERROR: No input provided.")
        sys.exit(1)

    code = _extract_code(raw)
    print("\nExchanging authorization code for tokens...")
    token_payload = _exchange_code(client_id, client_secret, code)

    access_token = token_payload["access_token"]
    refresh_token = token_payload.get("refresh_token", "")
    expires_in = token_payload.get("expires_in", 5183999)
    token_expiry = int(time.time()) + expires_in

    print("Fetching your LinkedIn profile...")
    person_urn = _fetch_person_urn(access_token)

    set_key(str(_ENV_PATH), "LINKEDIN_ACCESS_TOKEN", access_token)
    set_key(str(_ENV_PATH), "LINKEDIN_REFRESH_TOKEN", refresh_token)
    set_key(str(_ENV_PATH), "LINKEDIN_TOKEN_EXPIRY", str(token_expiry))
    set_key(str(_ENV_PATH), "LINKEDIN_PERSON_URN", person_urn)

    print("\n--- Setup complete ---\n")
    print(f"  Person URN : {person_urn}")
    print(f"  Token expires in {expires_in // 86400} days")
    if not refresh_token:
        print(
            "\nWARNING: No refresh_token was returned. This can happen if your LinkedIn app "
            "does not have the 'r_emailaddress' scope or the token was already issued recently. "
            "You may need to re-run this script after the access token expires."
        )
    print("\nYou can now start the server: python server.py\n")


if __name__ == "__main__":
    main()
