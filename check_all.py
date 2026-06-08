#!/usr/bin/env python3
"""
Health check for all social MCP servers.
Calls get_account_info on each platform — read-only, nothing is published.
Run from the repo root: python check_all.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent

_LINKEDIN_CHECK = """
import asyncio, json
from pathlib import Path
from auth import TokenManager
from api import LinkedInClient

async def main():
    tm = TokenManager(Path(".env"))
    client = LinkedInClient(tm)
    profile = await client.get_profile()
    print(json.dumps({"success": True, "data": profile.model_dump()}))

asyncio.run(main())
"""

_INSTAGRAM_CHECK = """
import asyncio, json
from pathlib import Path
from dotenv import dotenv_values
from auth import TokenManager
from api import InstagramClient

async def main():
    env = dotenv_values(Path(".env"))
    tm = TokenManager(Path(".env"))
    client = InstagramClient(tm, env["INSTAGRAM_ACCOUNT_ID"])
    info = await client.get_account_info()
    print(json.dumps({"success": True, "data": info.model_dump()}))

asyncio.run(main())
"""

_FACEBOOK_CHECK = """
import asyncio, json
from pathlib import Path
from dotenv import dotenv_values
from auth import TokenManager
from api import FacebookClient

async def main():
    env = dotenv_values(Path(".env"))
    tm = TokenManager(Path(".env"))
    client = FacebookClient(tm, env["FACEBOOK_PAGE_ID"])
    info = await client.get_page_info()
    print(json.dumps({"success": True, "data": info.model_dump()}))

asyncio.run(main())
"""

_WORDPRESS_CHECK = """
import asyncio, json
from pathlib import Path
from dotenv import dotenv_values
from auth import TokenManager
from api import WordPressClient

async def main():
    env = dotenv_values(Path(".env"))
    tm = TokenManager(Path(".env"))
    client = WordPressClient(tm, env["WP_SITE_ID"])
    info = await client.get_site_info()
    print(json.dumps({"success": True, "data": info.model_dump()}))

asyncio.run(main())
"""

_THREADS_CHECK = """
import asyncio, json
from pathlib import Path
from dotenv import dotenv_values
from auth import TokenManager
from api import ThreadsClient

async def main():
    env = dotenv_values(Path(".env"))
    tm = TokenManager(Path(".env"))
    client = ThreadsClient(tm, env["THREADS_USER_ID"])
    info = await client.get_account_info()
    print(json.dumps({"success": True, "data": info.model_dump()}))

asyncio.run(main())
"""

_PLATFORMS: list[tuple[str, str]] = [
    ("linkedin", _LINKEDIN_CHECK),
    ("instagram", _INSTAGRAM_CHECK),
    ("facebook", _FACEBOOK_CHECK),
    ("wordpress", _WORDPRESS_CHECK),
    ("threads", _THREADS_CHECK),
]


def _check(platform: str, script: str) -> dict:
    env_path = ROOT / platform / ".env"
    if not env_path.exists():
        return {"success": False, "error": ".env not found — run setup first"}

    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT / platform,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout after 20s"}

    if result.returncode == 0 and result.stdout.strip():
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return {"success": False, "error": result.stdout.strip()}

    stderr = result.stderr.strip()
    last_line = stderr.splitlines()[-1] if stderr else "unknown error"
    return {"success": False, "error": last_line}


def main() -> None:
    print("\nSocial MCP — Health Check")
    print("=" * 45)
    all_ok = True
    for platform, script in _PLATFORMS:
        result = _check(platform, script)
        ok = result.get("success", False)
        if not ok:
            all_ok = False
        icon = "OK  " if ok else "FAIL"
        print(f"\n[{icon}] {platform.upper()}")
        if ok:
            for k, v in (result.get("data") or {}).items():
                print(f"      {k}: {v}")
        else:
            print(f"      Error: {result.get('error', 'unknown')}")

    print("\n" + "=" * 45)
    if all_ok:
        print("All platforms operational.\n")
    else:
        print("Some platforms need attention.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
