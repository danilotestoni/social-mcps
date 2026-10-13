from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import config


class SecretVersionRotationTests(TestCase):
    parent = "projects/test-project/secrets/test-secret"
    required_permissions = list(config._REQUIRED_SECRET_PERMISSIONS)

    def setUp(self) -> None:
        self.env = patch.dict(
            os.environ,
            {
                config.CONSOLIDATED_SECRETS_ENV_VAR: '{"OTHER_TOKEN":"keep"}',
                config.CONSOLIDATED_SECRET_NAME_ENV_VAR: "test-secret",
                "GOOGLE_CLOUD_PROJECT": "test-project",
                "LINKEDIN_REFRESH_TOKEN": "old-refresh",
            },
            clear=True,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    @staticmethod
    def response(name: str, data: dict[str, str]):
        return SimpleNamespace(name=name, payload=SimpleNamespace(data=json.dumps(data).encode()))

    def test_writes_verifies_and_destroys_every_superseded_version(self) -> None:
        v6 = f"{self.parent}/versions/6"
        v7 = f"{self.parent}/versions/7"
        client = SimpleNamespace(
            test_iam_permissions=Mock(
                return_value=SimpleNamespace(permissions=self.required_permissions)
            ),
            access_secret_version=Mock(
                side_effect=[
                    self.response(v6, {"OTHER_TOKEN": "keep", "LINKEDIN_REFRESH_TOKEN": "old"}),
                    self.response(v7, {"OTHER_TOKEN": "keep", "LINKEDIN_REFRESH_TOKEN": "new"}),
                    self.response(v7, {"OTHER_TOKEN": "keep", "LINKEDIN_REFRESH_TOKEN": "new"}),
                ]
            ),
            add_secret_version=Mock(return_value=SimpleNamespace(name=v7)),
            list_secret_versions=Mock(
                return_value=[
                    SimpleNamespace(name=v6, state=1),
                    SimpleNamespace(name=f"{self.parent}/versions/5", state=2),
                    SimpleNamespace(name=f"{self.parent}/versions/4", state=3),
                    SimpleNamespace(name=v7, state=1),
                    # A concurrent/manual rotation after the latest check must survive.
                    SimpleNamespace(name=f"{self.parent}/versions/8", state=1),
                ]
            ),
            destroy_secret_version=Mock(),
        )

        with patch("core.config._secret_client", return_value=client):
            config.persist_values(Path("unused.env"), {"LINKEDIN_REFRESH_TOKEN": "new"})

        client.add_secret_version.assert_called_once()
        client.destroy_secret_version.assert_any_call(request={"name": v6})
        client.destroy_secret_version.assert_any_call(
            request={"name": f"{self.parent}/versions/5"}
        )
        self.assertEqual(client.destroy_secret_version.call_count, 2)
        destroyed_names = {
            call.kwargs["request"]["name"]
            for call in client.destroy_secret_version.call_args_list
        }
        self.assertNotIn(f"{self.parent}/versions/8", destroyed_names)
        self.assertEqual(
            json.loads(os.environ[config.CONSOLIDATED_SECRETS_ENV_VAR]),
            {"OTHER_TOKEN": "keep", "LINKEDIN_REFRESH_TOKEN": "new"},
        )

    def test_missing_cloud_metadata_fails_without_ephemeral_fallback(self) -> None:
        os.environ.pop(config.CONSOLIDATED_SECRET_NAME_ENV_VAR)

        with patch("core.config._persist_env_file") as persist_env, self.assertRaises(
            config.SecretPersistenceError
        ):
            config.persist_values(Path("unused.env"), {"LINKEDIN_REFRESH_TOKEN": "new"})

        persist_env.assert_not_called()

    def test_mismatched_readback_does_not_destroy_old_versions(self) -> None:
        v6 = f"{self.parent}/versions/6"
        v7 = f"{self.parent}/versions/7"
        client = SimpleNamespace(
            test_iam_permissions=Mock(
                return_value=SimpleNamespace(permissions=self.required_permissions)
            ),
            access_secret_version=Mock(
                side_effect=[
                    self.response(v6, {"LINKEDIN_REFRESH_TOKEN": "old"}),
                    self.response(v7, {"LINKEDIN_REFRESH_TOKEN": "wrong"}),
                ]
            ),
            add_secret_version=Mock(return_value=SimpleNamespace(name=v7)),
            destroy_secret_version=Mock(),
        )

        with patch("core.config._secret_client", return_value=client), self.assertRaises(
            config.SecretPersistenceError
        ):
            config.persist_values(Path("unused.env"), {"LINKEDIN_REFRESH_TOKEN": "new"})

        client.destroy_secret_version.assert_not_called()
        self.assertEqual(os.environ["LINKEDIN_REFRESH_TOKEN"], "old-refresh")

    def test_missing_destroy_permission_fails_before_adding_a_version(self) -> None:
        client = SimpleNamespace(
            test_iam_permissions=Mock(
                return_value=SimpleNamespace(
                    permissions=["secretmanager.versions.access"]
                )
            ),
            add_secret_version=Mock(),
        )

        with patch("core.config._secret_client", return_value=client), self.assertRaises(
            config.SecretPersistenceError
        ):
            config.persist_values(Path("unused.env"), {"LINKEDIN_REFRESH_TOKEN": "new"})

        client.add_secret_version.assert_not_called()

    def test_social_token_pairs_are_persisted_atomically(self) -> None:
        from auth.facebook_auth import FacebookTokenManager
        from auth.instagram_auth import InstagramTokenManager
        from auth.threads_auth import ThreadsTokenManager

        cases = [
            (FacebookTokenManager, "auth.facebook_auth", "FACEBOOK_ACCESS_TOKEN", "FACEBOOK_TOKEN_EXPIRY"),
            (InstagramTokenManager, "auth.instagram_auth", "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_TOKEN_EXPIRY"),
            (ThreadsTokenManager, "auth.threads_auth", "THREADS_ACCESS_TOKEN", "THREADS_TOKEN_EXPIRY"),
        ]
        token_data = SimpleNamespace(access_token="new-access", token_expiry=1234567890)

        for manager_type, module_name, access_key, expiry_key in cases:
            with self.subTest(platform=access_key.split("_", 1)[0]):
                manager = manager_type(Path("unused.env"))
                with patch(f"{module_name}.persist_values") as persist_values:
                    manager.persist(token_data)

                persist_values.assert_called_once_with(
                    Path("unused.env"),
                    {access_key: "new-access", expiry_key: "1234567890"},
                )
