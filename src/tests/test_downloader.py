"""
Tests for uup_builder.downloader
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Stub uup_dump_api before importing
for mod in ("uup_dump_api", "uup_dump_api.adapter", "uup_dump_api.exceptions"):
    sys.modules.setdefault(mod, MagicMock())

from uup_builder.downloader import Downloader, _sha1, _human_size, DEFAULT_CONCURRENCY, DEFAULT_OUT  # noqa: E402


# ---------------------------------------------------------------------------
# _human_size helper
# ---------------------------------------------------------------------------

class TestHumanSize:
    def test_bytes(self):
        assert "B" in _human_size(500)

    def test_kilobytes(self):
        result = _human_size(2048)
        assert "KB" in result

    def test_megabytes(self):
        result = _human_size(5 * 1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self):
        result = _human_size(3 * 1024 ** 3)
        assert "GB" in result

    def test_zero_bytes(self):
        result = _human_size(0)
        assert "B" in result


# ---------------------------------------------------------------------------
# _sha1 helper
# ---------------------------------------------------------------------------

class TestSha1:
    def test_correct_hash(self, tmp_path):
        f = tmp_path / "test.bin"
        content = b"hello uup builder"
        f.write_bytes(content)
        expected = hashlib.sha1(content).hexdigest()
        assert _sha1(f) == expected

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        expected = hashlib.sha1(b"").hexdigest()
        assert _sha1(f) == expected


# ---------------------------------------------------------------------------
# Downloader.__init__
# ---------------------------------------------------------------------------

class TestDownloaderInit:
    def test_defaults(self):
        dl = Downloader()
        assert dl.out_dir == Path(DEFAULT_OUT)
        assert dl.concurrency == DEFAULT_CONCURRENCY
        assert dl.no_resume is False

    def test_custom_values(self, tmp_path):
        dl = Downloader(out_dir=tmp_path, concurrency=8, no_resume=True)
        assert dl.out_dir == tmp_path
        assert dl.concurrency == 8
        assert dl.no_resume is True

    def test_string_out_dir_converted_to_path(self, tmp_path):
        dl = Downloader(out_dir=str(tmp_path))
        assert isinstance(dl.out_dir, Path)


# ---------------------------------------------------------------------------
# Downloader.download_all — validation
# ---------------------------------------------------------------------------

class TestDownloadAllValidation:
    def test_empty_files_exits(self):
        dl = Downloader()
        with pytest.raises(SystemExit):
            dl.download_all({"files": {}})

    def test_missing_files_key_exits(self):
        dl = Downloader()
        with pytest.raises(SystemExit):
            dl.download_all({})


# ---------------------------------------------------------------------------
# Downloader.download_all — no_resume deletes existing files
# ---------------------------------------------------------------------------

class TestDownloadAllNoResume:
    def test_existing_file_deleted_when_no_resume(self, tmp_path):
        existing = tmp_path / "somefile.esd"
        existing.write_bytes(b"partial data")

        dl = Downloader(out_dir=tmp_path, no_resume=True)
        file_data = {
            "updateName": "Test",
            "arch": "amd64",
            "build": "12345",
            "files": {
                "somefile.esd": {"url": "http://example.com/somefile.esd", "sha1": None, "size": "0"},
            },
        }

        # Patch _download_plain to avoid real HTTP
        with patch.object(dl, "_download_plain", return_value=[]) as mock_dl:
            dl.download_all(file_data)

        assert not existing.exists()

    def test_existing_file_kept_when_resume(self, tmp_path):
        existing = tmp_path / "somefile.esd"
        existing.write_bytes(b"partial data")

        dl = Downloader(out_dir=tmp_path, no_resume=False)
        file_data = {
            "updateName": "Test",
            "arch": "amd64",
            "build": "12345",
            "files": {
                "somefile.esd": {"url": "http://example.com/somefile.esd", "sha1": None, "size": "0"},
            },
        }

        with patch.object(dl, "_download_plain", return_value=[]):
            dl.download_all(file_data)

        assert existing.exists()


# ---------------------------------------------------------------------------
# Downloader._download_plain
# ---------------------------------------------------------------------------

class TestDownloadPlain:
    def _fake_download_one(self, ok=True):
        """Return a patched _download_one that succeeds or fails."""
        def _inner(url, dest, sha1, progress=None, overall_task=None):
            if ok:
                dest.write_bytes(b"data")
            return dest.name, ok
        return _inner

    def test_all_success(self, tmp_path):
        dl = Downloader(out_dir=tmp_path)
        tasks = [("file1.esd", "http://x/1", tmp_path / "file1.esd", None)]
        with patch("uup_builder.downloader._download_one", side_effect=self._fake_download_one(True)):
            failed = dl._download_plain(tasks)
        assert failed == []

    def test_failure_recorded(self, tmp_path):
        dl = Downloader(out_dir=tmp_path)
        tasks = [("file1.esd", "http://x/1", tmp_path / "file1.esd", None)]
        with patch("uup_builder.downloader._download_one", side_effect=self._fake_download_one(False)):
            failed = dl._download_plain(tasks)
        assert "file1.esd" in failed