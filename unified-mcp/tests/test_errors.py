from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.errors import describe_exception


class DescribeExceptionTests(TestCase):
    def test_returns_message_when_present(self) -> None:
        exc = ValueError("something broke")

        self.assertEqual(describe_exception(exc), "something broke")

    def test_falls_back_to_type_name_when_message_is_empty(self) -> None:
        class _SilentTimeout(Exception):
            pass

        exc = _SilentTimeout()

        result = describe_exception(exc)

        self.assertIn("_SilentTimeout", result)
        self.assertNotEqual(result, "")
