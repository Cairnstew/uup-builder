"""
Tests for uup_builder.interactive
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

for mod in ("uup_dump_api", "uup_dump_api.adapter", "uup_dump_api.exceptions"):
    sys.modules.setdefault(mod, MagicMock())

# Force HAS_RICH = False so we exercise the plain-text path
with patch.dict(sys.modules, {"rich": None, "rich.prompt": None, "rich.table": None}):
    import importlib
    import uup_builder.output as _out
    _out.HAS_RICH = False
    import uup_builder.interactive as interactive_mod
    importlib.reload(interactive_mod)

from uup_builder.interactive import pick_build, pick_lang, pick_edition  # noqa: E402


def _make_client(**overrides):
    client = MagicMock()
    client.list_builds.return_value = [
        {"uuid": "uuid-1", "title": "Windows 11 22H2", "build": "22621", "arch": "amd64"},
        {"uuid": "uuid-2", "title": "Windows 10 21H2", "build": "19044", "arch": "amd64"},
    ]
    client.list_langs.return_value = (
        ["en-us", "de-de"],
        {"en-us": "English (US)", "de-de": "German"},
    )
    client.list_editions.return_value = (
        ["professional", "core"],
        {"professional": "Windows Pro", "core": "Windows Home"},
    )
    for k, v in overrides.items():
        setattr(client, k, v)
    return client


# ---------------------------------------------------------------------------
# pick_build
# ---------------------------------------------------------------------------

class TestPickBuild:
    def test_returns_selected_build(self):
        client = _make_client()
        with patch("builtins.input", return_value="1"):
            result = pick_build(client)
        assert result["uuid"] == "uuid-1"

    def test_second_option(self):
        client = _make_client()
        with patch("builtins.input", return_value="2"):
            result = pick_build(client)
        assert result["uuid"] == "uuid-2"

    def test_empty_input_defaults_to_first(self):
        client = _make_client()
        with patch("builtins.input", return_value=""):
            result = pick_build(client)
        assert result["uuid"] == "uuid-1"

    def test_out_of_range_clamped(self):
        client = _make_client()
        with patch("builtins.input", return_value="99"):
            result = pick_build(client)
        # clamped to len(builds) = 2
        assert result["uuid"] == "uuid-2"

    def test_passes_search_to_client(self):
        client = _make_client()
        with patch("builtins.input", return_value="1"):
            pick_build(client, search="Windows 11")
        client.list_builds.assert_called_once_with(search="Windows 11", sort_by_date=True)

    def test_no_builds_exits(self):
        client = _make_client()
        client.list_builds.return_value = []
        with pytest.raises(SystemExit):
            pick_build(client)


# ---------------------------------------------------------------------------
# pick_lang
# ---------------------------------------------------------------------------

class TestPickLang:
    def test_returns_selected_lang(self):
        client = _make_client()
        with patch("builtins.input", return_value="2"):
            result = pick_lang(client, "some-uuid")
        assert result == "de-de"

    def test_default_first_lang(self):
        client = _make_client()
        with patch("builtins.input", return_value=""):
            result = pick_lang(client, "some-uuid")
        assert result == "en-us"

    def test_no_langs_exits(self):
        client = _make_client()
        client.list_langs.return_value = ([], {})
        with pytest.raises(SystemExit):
            pick_lang(client, "some-uuid")


# ---------------------------------------------------------------------------
# pick_edition
# ---------------------------------------------------------------------------

class TestPickEdition:
    def test_returns_selected_edition(self):
        client = _make_client()
        with patch("builtins.input", return_value="1"):
            result = pick_edition(client, "some-uuid", "en-us")
        assert result == "professional"

    def test_second_edition(self):
        client = _make_client()
        with patch("builtins.input", return_value="2"):
            result = pick_edition(client, "some-uuid", "en-us")
        assert result == "core"

    def test_no_editions_exits(self):
        client = _make_client()
        client.list_editions.return_value = ([], {})
        with pytest.raises(SystemExit):
            pick_edition(client, "some-uuid", "en-us")