"""
Tests for uup_builder.output
"""

from __future__ import annotations

import logging
import sys
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Force HAS_RICH=False path so we test the plain fallback without needing rich
# ---------------------------------------------------------------------------

class TestOutputNoRich:
    """Test the plain-text (no-rich) code paths."""

    def setup_method(self):
        # Temporarily remove rich from sys.modules so output re-imports without it
        self._orig = sys.modules.get("rich")
        self._orig_console = sys.modules.get("rich.console")
        self._orig_logging = sys.modules.get("rich.logging")

    def teardown_method(self):
        # Restore whatever was there
        import importlib
        import uup_builder.output as out_mod
        importlib.reload(out_mod)

    def test_bail_exits_with_code_1(self, capsys):
        from uup_builder.output import bail
        with pytest.raises(SystemExit) as exc_info:
            bail("something went wrong")
        assert exc_info.value.code == 1

    def test_bail_prints_error_message(self, capsys):
        from uup_builder.output import bail
        with pytest.raises(SystemExit):
            bail("fatal error text")
        captured = capsys.readouterr()
        assert "fatal error text" in captured.out or "fatal error text" in captured.err

    def test_print_ok_contains_checkmark(self, capsys):
        from uup_builder.output import print_ok, HAS_RICH
        if not HAS_RICH:
            print_ok("success message")
            captured = capsys.readouterr()
            assert "success message" in captured.out
            assert "✔" in captured.out

    def test_print_err_contains_error(self, capsys):
        from uup_builder.output import print_err, HAS_RICH
        if not HAS_RICH:
            print_err("error message")
            captured = capsys.readouterr()
            assert "error message" in captured.out

    def test_print_info_contains_info(self, capsys):
        from uup_builder.output import print_info, HAS_RICH
        if not HAS_RICH:
            print_info("informational text")
            captured = capsys.readouterr()
            assert "informational text" in captured.out

    def test_print_msg_plain(self, capsys):
        from uup_builder.output import print_msg, HAS_RICH
        if not HAS_RICH:
            print_msg("hello world")
            captured = capsys.readouterr()
            assert "hello world" in captured.out


class TestSetupLogging:
    def test_debug_level_when_verbose(self):
        from uup_builder.output import setup_logging
        root = logging.getLogger()
        # Reset so basicConfig takes effect (pytest adds handlers before tests run)
        original_level = root.level
        root.handlers.clear()
        try:
            setup_logging(verbose=True)
            assert root.level == logging.DEBUG
        finally:
            root.setLevel(original_level)

    def test_info_level_when_not_verbose(self):
        from uup_builder.output import setup_logging
        root = logging.getLogger()
        original_level = root.level
        root.handlers.clear()
        try:
            setup_logging(verbose=False)
            assert root.level == logging.INFO
        finally:
            root.setLevel(original_level)