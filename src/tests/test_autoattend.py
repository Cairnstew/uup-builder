"""
tests.test_autounattend
~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for uup_builder.autounattend.AnswerFile.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from uup_builder.autounattend import AnswerFile, _ANSWER_FILE_NAME


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def xml_file(tmp_path: Path) -> Path:
    """A minimal valid XML answer file."""
    f = tmp_path / "autounattend.xml"
    f.write_text('<?xml version="1.0" encoding="utf-8"?><unattend/>', encoding="utf-8")
    return f


@pytest.fixture()
def uup_dir(tmp_path: Path) -> Path:
    """An empty directory standing in for the UUP working directory."""
    d = tmp_path / "UUPs"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# AnswerFile.__init__
# ---------------------------------------------------------------------------

class TestAnswerFileInit:
    def test_accepts_valid_xml(self, xml_file: Path) -> None:
        af = AnswerFile(xml_file)
        assert af.path == xml_file.resolve()

    def test_accepts_string_path(self, xml_file: Path) -> None:
        af = AnswerFile(str(xml_file))
        assert af.path == xml_file.resolve()

    def test_expands_home_tilde(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """~ should be expanded using the process home directory."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        answer = fake_home / "answer.xml"
        answer.write_text("<unattend/>", encoding="utf-8")

        monkeypatch.setenv("HOME", str(fake_home))
        af = AnswerFile("~/answer.xml")
        assert af.path.exists()

    def test_raises_if_file_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Answer file not found"):
            AnswerFile(tmp_path / "nonexistent.xml")

    def test_raises_if_not_xml_extension(self, tmp_path: Path) -> None:
        bad = tmp_path / "answer.txt"
        bad.write_text("<unattend/>", encoding="utf-8")
        with pytest.raises(ValueError, match="Answer file must be an XML file"):
            AnswerFile(bad)

    def test_raises_for_no_extension(self, tmp_path: Path) -> None:
        bad = tmp_path / "answer"
        bad.write_text("<unattend/>", encoding="utf-8")
        with pytest.raises(ValueError, match="Answer file must be an XML file"):
            AnswerFile(bad)

    def test_case_insensitive_extension(self, tmp_path: Path) -> None:
        """Both .XML and .xml should be accepted."""
        f = tmp_path / "answer.XML"
        f.write_text("<unattend/>", encoding="utf-8")
        af = AnswerFile(f)
        assert af.path.exists()


# ---------------------------------------------------------------------------
# AnswerFile.inject
# ---------------------------------------------------------------------------

class TestAnswerFileInject:
    def test_copies_file_to_uup_dir(self, xml_file: Path, uup_dir: Path) -> None:
        af = AnswerFile(xml_file)
        dest = af.inject(uup_dir)
        assert dest.exists()

    def test_destination_named_autounattend_xml(self, xml_file: Path, uup_dir: Path) -> None:
        af = AnswerFile(xml_file)
        dest = af.inject(uup_dir)
        assert dest.name == _ANSWER_FILE_NAME

    def test_destination_inside_uup_dir(self, xml_file: Path, uup_dir: Path) -> None:
        af = AnswerFile(xml_file)
        dest = af.inject(uup_dir)
        assert dest.parent.resolve() == uup_dir.resolve()

    def test_content_preserved(self, xml_file: Path, uup_dir: Path) -> None:
        original = xml_file.read_text(encoding="utf-8")
        af = AnswerFile(xml_file)
        dest = af.inject(uup_dir)
        assert dest.read_text(encoding="utf-8") == original

    def test_returns_path_object(self, xml_file: Path, uup_dir: Path) -> None:
        af = AnswerFile(xml_file)
        dest = af.inject(uup_dir)
        assert isinstance(dest, Path)

    def test_accepts_string_uup_dir(self, xml_file: Path, uup_dir: Path) -> None:
        af = AnswerFile(xml_file)
        dest = af.inject(str(uup_dir))
        assert dest.exists()

    def test_overwrites_existing_answer_file(self, xml_file: Path, uup_dir: Path) -> None:
        """Injecting twice should overwrite silently."""
        (uup_dir / _ANSWER_FILE_NAME).write_text("<old/>", encoding="utf-8")
        af = AnswerFile(xml_file)
        dest = af.inject(uup_dir)
        assert "<old/>" not in dest.read_text(encoding="utf-8")

    def test_source_file_unchanged_after_inject(self, xml_file: Path, uup_dir: Path) -> None:
        original = xml_file.read_text(encoding="utf-8")
        AnswerFile(xml_file).inject(uup_dir)
        assert xml_file.read_text(encoding="utf-8") == original