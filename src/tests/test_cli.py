"""
Tests for uup_builder.cli  (argument parsing + command dispatch)
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, call

import pytest

for mod in ("uup_dump_api", "uup_dump_api.adapter", "uup_dump_api.exceptions"):
    sys.modules.setdefault(mod, MagicMock())

from uup_builder.cli import build_parser, main  # noqa: E402


# ---------------------------------------------------------------------------
# Argument parser structure
# ---------------------------------------------------------------------------

class TestBuildParser:
    def _parse(self, *args):
        return build_parser().parse_args(list(args))

    # -- list ----------------------------------------------------------------

    def test_list_no_args(self):
        ns = self._parse("list")
        assert ns.command == "list"
        assert ns.search is None
        assert ns.sort_by_date is False

    def test_list_with_search(self):
        ns = self._parse("list", "--search", "Windows 11")
        assert ns.search == "Windows 11"

    def test_list_sort_by_date(self):
        ns = self._parse("list", "--sort-by-date")
        assert ns.sort_by_date is True

    # -- langs ---------------------------------------------------------------

    def test_langs_requires_id(self):
        with pytest.raises(SystemExit):
            self._parse("langs")

    def test_langs_with_id(self):
        ns = self._parse("langs", "--id", "my-uuid")
        assert ns.id == "my-uuid"

    # -- editions ------------------------------------------------------------

    def test_editions_requires_id_and_lang(self):
        with pytest.raises(SystemExit):
            self._parse("editions", "--id", "uuid")
        with pytest.raises(SystemExit):
            self._parse("editions", "--lang", "en-us")

    def test_editions_with_all_args(self):
        ns = self._parse("editions", "--id", "uuid", "--lang", "en-us")
        assert ns.id == "uuid"
        assert ns.lang == "en-us"

    # -- download ------------------------------------------------------------

    def test_download_defaults(self):
        ns = self._parse("download")
        assert ns.id is None
        assert ns.lang is None
        assert ns.edition is None
        assert ns.no_resume is False

    def test_download_all_args(self):
        ns = self._parse(
            "download",
            "--id", "uuid", "--lang", "en-us", "--edition", "professional",
            "--out", "/tmp/uups", "--concurrency", "8", "--no-resume",
        )
        assert ns.id == "uuid"
        assert ns.concurrency == 8
        assert ns.no_resume is True

    # -- convert -------------------------------------------------------------

    def test_convert_defaults(self):
        ns = self._parse("convert")
        assert ns.compress == "wim"
        assert ns.iso_out is None

    def test_convert_esd_compression(self):
        ns = self._parse("convert", "--compress", "esd")
        assert ns.compress == "esd"

    def test_convert_invalid_compress(self):
        with pytest.raises(SystemExit):
            self._parse("convert", "--compress", "zip")

    # -- build ---------------------------------------------------------------

    def test_build_defaults(self):
        ns = self._parse("build")
        assert ns.command == "build"
        assert ns.no_convert is False
        assert ns.compress == "wim"

    def test_build_no_convert_flag(self):
        ns = self._parse("build", "--no-convert")
        assert ns.no_convert is True

    def test_build_with_id_lang_edition(self):
        ns = self._parse("build", "--id", "uuid", "--lang", "en-us", "--edition", "professional")
        assert ns.id == "uuid"
        assert ns.lang == "en-us"
        assert ns.edition == "professional"

    # -- missing subcommand --------------------------------------------------

    def test_no_subcommand_exits(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    # -- verbose flag --------------------------------------------------------

    def test_verbose_flag(self):
        ns = self._parse("list", "--verbose")
        assert ns.verbose is True

    def test_verbose_short_flag(self):
        ns = self._parse("list", "-v")
        assert ns.verbose is True


# ---------------------------------------------------------------------------
# cmd_list
# ---------------------------------------------------------------------------

class TestCmdList:
    def test_prints_no_builds_found(self, capsys):
        from uup_builder.cli import cmd_list
        args = MagicMock(verbose=False, search=None, sort_by_date=False)
        with patch("uup_builder.cli.UUPClient") as MockClient:
            MockClient.return_value.list_builds.return_value = []
            cmd_list(args)
        captured = capsys.readouterr()
        assert "No builds found" in captured.out

    def test_prints_builds_plain(self, capsys):
        from uup_builder.cli import cmd_list
        import uup_builder.cli as cli_mod
        cli_mod.HAS_RICH = False

        args = MagicMock(verbose=False, search=None, sort_by_date=False)
        with patch("uup_builder.cli.UUPClient") as MockClient:
            MockClient.return_value.list_builds.return_value = [
                {"uuid": "uuid-1", "title": "Windows 11", "build": "22621", "arch": "amd64"}
            ]
            cmd_list(args)
        captured = capsys.readouterr()
        assert "Windows 11" in captured.out


# ---------------------------------------------------------------------------
# cmd_build — no-convert path
# ---------------------------------------------------------------------------

class TestCmdBuild:
    def test_no_convert_skips_converter(self, capsys):
        from uup_builder.cli import cmd_build
        args = MagicMock(
            verbose=False, id="uuid", lang="en-us", edition="professional",
            out="./UUPs", concurrency=4, no_resume=False,
            compress="wim", iso_out=None, no_convert=True,
        )
        with patch("uup_builder.cli.UUPClient") as MockClient, \
             patch("uup_builder.cli.Downloader") as MockDl, \
             patch("uup_builder.cli.Converter") as MockCv:
            MockClient.return_value.get_files.return_value = {
                "updateName": "Test", "arch": "amd64", "build": "12345", "files": {}
            }
            MockDl.return_value.download_all.return_value = []
            cmd_build(args)
        MockCv.assert_not_called()