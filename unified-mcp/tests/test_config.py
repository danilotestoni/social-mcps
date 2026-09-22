from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import CONSOLIDATED_SECRETS_ENV_VAR, load_consolidated_secrets


class LoadConsolidatedSecretsTests(TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.pop(CONSOLIDATED_SECRETS_ENV_VAR, None)
        self._probe_keys = ("PROBE_FOO", "PROBE_BAR")
        for key in self._probe_keys:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key in self._probe_keys:
            os.environ.pop(key, None)
        if self._saved is not None:
            os.environ[CONSOLIDATED_SECRETS_ENV_VAR] = self._saved

    def test_noop_when_env_var_absent(self) -> None:
        load_consolidated_secrets()

        self.assertNotIn("PROBE_FOO", os.environ)

    def test_populates_environ_from_json(self) -> None:
        load_consolidated_secrets(raw='{"PROBE_FOO": "a", "PROBE_BAR": "b"}')

        self.assertEqual(os.environ["PROBE_FOO"], "a")
        self.assertEqual(os.environ["PROBE_BAR"], "b")

    def test_does_not_override_existing_env_var(self) -> None:
        os.environ["PROBE_FOO"] = "already-set"

        load_consolidated_secrets(raw='{"PROBE_FOO": "from-json"}')

        self.assertEqual(os.environ["PROBE_FOO"], "already-set")

    def test_invalid_json_is_non_fatal(self) -> None:
        load_consolidated_secrets(raw="not json")

        self.assertNotIn("PROBE_FOO", os.environ)
