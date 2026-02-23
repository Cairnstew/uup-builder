"""
Tests for uup_builder.converter
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import requests

# Stub heavy dependencies before importing
for mod in ("uup_dump_api", "uup_dump_api.adapter", "uup_dump_api.exceptions"):
    stub = MagicMock()
    stub.exceptions = MagicMock()
    for exc_name in ("UUPDumpAPIError", "UUPDumpConnectionError",
                     "UUPDumpResponseError", "UUPDumpTimeoutError"):
        setattr(stub.exceptions, exc_name, type(exc_name, (Exception,), {}))
    sys.modules.setdefault(mod, stub)

from uup_builder.converter import (  # noqa: E402
    CONVERT_SH_URL,
    CONVERT_VE_PLUGIN_URL,
    Converter,
    _DEFAULT_CACHE,
    _ISO_BINS,
    _REQUIRED_BINS,
)


# ---------------------------------------------------------------------------
# Converter.__init__
# ---------------------------------------------------------------------------

class TestConverterInit:
    def test_default_compress(self):
        assert Converter().compress == "wim"

    def test_esd_compress(self):
        assert Converter(compress="esd").compress == "esd"

    def test_invalid_compress_exits(self):
        with pytest.raises(SystemExit):
            Converter(compress="zip")

    def test_default_cache_dir(self):
        assert Converter().cache_dir == _DEFAULT_CACHE

    def test_custom_cache_dir(self, tmp_path):
        c = Converter(cache_dir=tmp_path)
        assert c.cache_dir == tmp_path

    def test_virtual_editions_default_false(self):
        assert Converter().virtual_editions is False

    def test_virtual_editions_true(self):
        assert Converter(virtual_editions=True).virtual_editions is True


# ---------------------------------------------------------------------------
# check_deps
# ---------------------------------------------------------------------------

class TestCheckDeps:
    def test_empty_when_all_present(self):
        with patch("shutil.which", return_value="/usr/bin/tool"):
            assert Converter().check_deps() == []

    def test_lists_missing_bins(self):
        def _which(name):
            return None if name in ("wimlib-imagex", "chntpw") else f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=_which):
            missing = Converter().check_deps()

        assert "wimlib-imagex" in missing
        assert "chntpw" in missing

    def test_no_iso_tool_reported(self):
        def _which(name):
            return None if name in _ISO_BINS else f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=_which):
            missing = Converter().check_deps()

        assert any("genisoimage" in m or "mkisofs" in m for m in missing)

    def test_only_one_iso_tool_needed(self):
        def _which(name):
            # genisoimage absent but mkisofs present
            return None if name == "genisoimage" else f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=_which):
            missing = Converter().check_deps()

        assert not any("mkisofs" in m or "genisoimage" in m for m in missing)


# ---------------------------------------------------------------------------
# ensure_script — download behaviour
# ---------------------------------------------------------------------------

class TestEnsureScript:
    def test_uses_cached_script_if_present(self, tmp_path):
        script = tmp_path / "convert.sh"
        script.write_text("#!/bin/bash\necho cached")

        with patch("requests.get") as mock_get:
            result = Converter(cache_dir=tmp_path).ensure_script()

        mock_get.assert_not_called()
        assert result == script

    def test_downloads_when_missing(self, tmp_path):
        fake_response = MagicMock()
        fake_response.content = b"#!/bin/bash\necho hello"
        fake_response.ok = True
        fake_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=fake_response) as mock_get:
            result = Converter(cache_dir=tmp_path).ensure_script()

        assert mock_get.call_args_list[0][0][0] == CONVERT_SH_URL
        assert result.exists()
        assert result.read_bytes() == b"#!/bin/bash\necho hello"

    def test_force_redownloads_existing_script(self, tmp_path):
        script = tmp_path / "convert.sh"
        script.write_text("old content")

        fake_response = MagicMock()
        fake_response.content = b"new content"
        fake_response.ok = True
        fake_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=fake_response):
            Converter(cache_dir=tmp_path).ensure_script(force=True)

        assert script.read_bytes() == b"new content"

    def test_script_is_executable(self, tmp_path):
        fake_response = MagicMock()
        fake_response.content = b"#!/bin/bash"
        fake_response.ok = True
        fake_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=fake_response):
            script = Converter(cache_dir=tmp_path).ensure_script()

        assert script.stat().st_mode & 0o111  # any execute bit set

    def test_network_error_exits(self, tmp_path):
        with patch("requests.get", side_effect=requests.RequestException("timeout")):
            with pytest.raises(SystemExit):
                Converter(cache_dir=tmp_path).ensure_script()

    def test_also_fetches_ve_plugin(self, tmp_path):
        responses = {
            CONVERT_SH_URL: MagicMock(content=b"#!/bin/bash", ok=True,
                                       raise_for_status=MagicMock()),
            CONVERT_VE_PLUGIN_URL: MagicMock(content=b"plugin", ok=True,
                                              raise_for_status=MagicMock()),
        }

        with patch("requests.get", side_effect=lambda url, **kw: responses[url]):
            Converter(cache_dir=tmp_path).ensure_script()

        assert (tmp_path / "convert_ve_plugin").exists()


# ---------------------------------------------------------------------------
# convert — argument passing and subprocess behaviour
# ---------------------------------------------------------------------------

class TestConvert:
    def _make_script(self, cache_dir: Path) -> Path:
        """Write a minimal fake convert.sh into cache_dir."""
        script = cache_dir / "convert.sh"
        script.write_text("#!/bin/bash\necho 'fake convert'\n")
        script.chmod(0o755)
        return script

    def test_raises_on_windows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        with pytest.raises(SystemExit):
            Converter(cache_dir=tmp_path).convert(uup_dir=tmp_path)

    def test_raises_if_uup_dir_missing(self, tmp_path):
        self._make_script(tmp_path)
        with patch("shutil.which", return_value="/usr/bin/tool"):
            with pytest.raises(SystemExit):
                Converter(cache_dir=tmp_path).convert(uup_dir=tmp_path / "nope")

    def test_passes_compress_to_script(self, tmp_path):
        uup_dir = tmp_path / "UUPs"
        uup_dir.mkdir()
        self._make_script(tmp_path)

        with patch("shutil.which", return_value="/usr/bin/tool"), \
             patch("uup_builder.deps.ensure_deps"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            Converter(compress="esd", cache_dir=tmp_path).convert(uup_dir=uup_dir)

        cmd = mock_run.call_args[0][0]
        assert "esd" in cmd

    def test_passes_virtual_editions_flag(self, tmp_path):
        uup_dir = tmp_path / "UUPs"
        uup_dir.mkdir()
        self._make_script(tmp_path)

        with patch("shutil.which", return_value="/usr/bin/tool"), \
             patch("uup_builder.deps.ensure_deps"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            Converter(virtual_editions=True, cache_dir=tmp_path).convert(uup_dir=uup_dir)

        cmd = mock_run.call_args[0][0]
        assert "1" in cmd  # virtual_editions=True → "1"

    def test_no_virtual_editions_passes_zero(self, tmp_path):
        uup_dir = tmp_path / "UUPs"
        uup_dir.mkdir()
        self._make_script(tmp_path)

        with patch("shutil.which", return_value="/usr/bin/tool"), \
             patch("uup_builder.deps.ensure_deps"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            Converter(virtual_editions=False, cache_dir=tmp_path).convert(uup_dir=uup_dir)

        cmd = mock_run.call_args[0][0]
        assert "0" in cmd

    def test_nonzero_exit_raises(self, tmp_path):
        uup_dir = tmp_path / "UUPs"
        uup_dir.mkdir()
        self._make_script(tmp_path)

        with patch("shutil.which", return_value="/usr/bin/tool"), \
             patch("uup_builder.deps.ensure_deps"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            with pytest.raises(SystemExit):
                Converter(cache_dir=tmp_path).convert(uup_dir=uup_dir)

    def test_uup_dir_passed_as_absolute(self, tmp_path):
        uup_dir = tmp_path / "UUPs"
        uup_dir.mkdir()
        self._make_script(tmp_path)

        with patch("shutil.which", return_value="/usr/bin/tool"), \
             patch("uup_builder.deps.ensure_deps"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            Converter(cache_dir=tmp_path).convert(uup_dir=uup_dir)

        cmd = mock_run.call_args[0][0]
        uup_dir_in_cmd = next(a for a in cmd if "UUPs" in str(a))
        assert Path(uup_dir_in_cmd).is_absolute()