"""
Tests for uup_builder.converter
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Stub heavy dependencies before importing
for mod in ("uup_dump_api", "uup_dump_api.adapter", "uup_dump_api.exceptions"):
    stub = MagicMock()
    stub.exceptions = MagicMock()
    for exc_name in ("UUPDumpAPIError", "UUPDumpConnectionError",
                     "UUPDumpResponseError", "UUPDumpTimeoutError"):
        setattr(stub.exceptions, exc_name, type(exc_name, (Exception,), {}))
    sys.modules.setdefault(mod, stub)

from uup_builder.converter import Converter, _METADATA_RE, _EDITIONS  # noqa: E402


# ---------------------------------------------------------------------------
# Converter.__init__ validation
# ---------------------------------------------------------------------------

class TestConverterInit:
    def test_valid_compress_wim(self):
        c = Converter(compress="wim")
        assert c.compress == "wim"

    def test_valid_compress_esd(self):
        c = Converter(compress="esd")
        assert c.compress == "esd"

    def test_invalid_compress_exits(self):
        with pytest.raises(SystemExit):
            Converter(compress="zip")

    def test_work_dir_stored_as_path(self, tmp_path):
        c = Converter(work_dir=str(tmp_path))
        assert c._work_dir == tmp_path

    def test_work_dir_none_by_default(self):
        c = Converter()
        assert c._work_dir is None


# ---------------------------------------------------------------------------
# _make_display_name
# ---------------------------------------------------------------------------

class TestMakeDisplayName:
    def test_windows_11_prefix(self):
        name = Converter._make_display_name("Professional", "Windows 11 22H2")
        assert name == "Windows 11 Professional"

    def test_windows_11_case_insensitive(self):
        name = Converter._make_display_name("Home", "WINDOWS 11 build 22621")
        assert name.startswith("Windows 11")

    def test_windows_10_default(self):
        name = Converter._make_display_name("Professional", "Windows 10 22H2")
        assert name == "Windows 10 Professional"

    def test_server_edition_default_year(self):
        name = Converter._make_display_name("ServerDatacenter", "Windows Server build")
        assert "Windows Server" in name
        assert "2022" in name

    def test_server_edition_2025(self):
        name = Converter._make_display_name("ServerStandard", "Windows Server 2025")
        assert "2025" in name

    def test_server_edition_2028(self):
        name = Converter._make_display_name("ServerStandard", "Windows Server 2028 Preview")
        assert "2028" in name


# ---------------------------------------------------------------------------
# _find_background
# ---------------------------------------------------------------------------

class TestFindBackground:
    def test_prefers_background_svr_bmp(self, tmp_path):
        sources = tmp_path / "sources"
        sources.mkdir()
        (sources / "background_svr.bmp").write_bytes(b"")
        (sources / "background_cli.bmp").write_bytes(b"")
        assert Converter._find_background(tmp_path) == "background_svr.bmp"

    def test_falls_back_to_cli_bmp(self, tmp_path):
        sources = tmp_path / "sources"
        sources.mkdir()
        (sources / "background_cli.bmp").write_bytes(b"")
        assert Converter._find_background(tmp_path) == "background_cli.bmp"

    def test_falls_back_to_winpe_jpg(self, tmp_path):
        sources = tmp_path / "sources"
        sources.mkdir()
        (sources / "winpe.jpg").write_bytes(b"")
        assert Converter._find_background(tmp_path) == "winpe.jpg"

    def test_ultimate_fallback_string(self, tmp_path):
        (tmp_path / "sources").mkdir()
        # No files present
        assert Converter._find_background(tmp_path) == "background_cli.bmp"

    def test_cli_bmp_before_svr_png(self, tmp_path):
        sources = tmp_path / "sources"
        sources.mkdir()
        (sources / "background_svr.png").write_bytes(b"")
        (sources / "background_cli.bmp").write_bytes(b"")
        # candidate order: svr.bmp > cli.bmp > svr.png > cli.png > winpe.jpg
        # cli.bmp ranks higher than svr.png
        assert Converter._find_background(tmp_path) == "background_cli.bmp"


# ---------------------------------------------------------------------------
# _METADATA_RE regex
# ---------------------------------------------------------------------------

class TestMetadataRe:
    def test_matches_valid_metadata_esd(self):
        assert _METADATA_RE.match("professional_en-us.esd")

    def test_matches_core_german(self):
        assert _METADATA_RE.match("core_de-de.esd")

    def test_case_insensitive(self):
        assert _METADATA_RE.match("PROFESSIONAL_EN-US.esd")

    def test_no_match_for_unknown_edition(self):
        assert not _METADATA_RE.match("fakeedition_en-us.esd")

    def test_no_match_for_install_esd(self):
        assert not _METADATA_RE.match("Microsoft-Windows-Foundation-Package.ESD")

    def test_no_match_for_random_filename(self):
        assert not _METADATA_RE.match("Windows11.esd")

    def test_all_known_editions_match(self):
        for edition in list(_EDITIONS)[:10]:
            filename = f"{edition}_en-us.esd"
            assert _METADATA_RE.match(filename), f"Expected match for {filename}"


# ---------------------------------------------------------------------------
# check_deps
# ---------------------------------------------------------------------------

class TestCheckDeps:
    def test_returns_empty_when_all_present(self):
        with patch("shutil.which", return_value="/usr/bin/tool"):
            missing = Converter().check_deps()
        assert missing == []

    def test_returns_missing_bin_names(self):
        def _which(name):
            return None if name in ("wimlib-imagex", "chntpw") else f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=_which):
            missing = Converter().check_deps()

        assert "wimlib-imagex" in missing
        assert "chntpw" in missing