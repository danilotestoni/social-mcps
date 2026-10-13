from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth.linkedin_auth import LinkedInTokenManager
from core.models import LinkedInTokenData


class LinkedInTokenPersistenceTests(TestCase):
    def test_refresh_persists_all_token_fields_in_one_call(self) -> None:
        token_data = LinkedInTokenData(
            access_token="access-new",
            refresh_token="refresh-new",
            expires_in=3600,
            token_expiry=1234567890,
        )
        manager = LinkedInTokenManager(Path("unused.env"))

        with patch("auth.linkedin_auth.persist_values") as persist_values:
            manager.persist(token_data)

        persist_values.assert_called_once_with(
            Path("unused.env"),
            {
                "LINKEDIN_ACCESS_TOKEN": "access-new",
                "LINKEDIN_REFRESH_TOKEN": "refresh-new",
                "LINKEDIN_TOKEN_EXPIRY": "1234567890",
            },
        )
