"""
Tests for uup_builder.deps
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

for mod in ("uup_dump_api", "uup_dump_api.adapter", "uup_dump_api.exceptions"):
    sys.modules.setdefault(mod, MagicMock())

from uup_builder.deps import ensure_deps, _detect_pm, _PKG_MAP, _install_hint  # noqa: E402


# ---------------------------------------------------------------------------
# _detect_pm
# ---------------------------------------------------------------------------

class TestDetectPm:
    def test_detects_apt(self):
        def _which(name):
            return "/usr/bin/apt-get" if name == "apt-get" else None

        with patch("platform.system", return_value="Linux"), \
             patch("shutil.which", side_effect=_which):
            pm = _detect_pm()

        assert pm == "apt"

    def test_detects_brew_on_macos(self):
        def _which(name):
            return "/opt/homebrew/bin/brew" if name == "brew" else None

        with patch("platform.system", return_value="Darwin"), \
             patch("shutil.which", side_effect=_which):
            pm = _detect_pm()

        assert pm == "brew"

    def test_detects_pacman(self):
        def _which(name):
            return "/usr/bin/pacman" if name == "pacman" else None

        with patch("platform.system", return_value="Linux"), \
             patch("shutil.which", side_effect=_which):
            pm = _detect_pm()

        assert pm == "pacman"

    def test_detects_dnf(self):
        def _which(name):
            return "/usr/bin/dnf" if name == "dnf" else None

        with patch("platform.system", return_value="Linux"), \
             patch("shutil.which", side_effect=_which):
            pm = _detect_pm()

        assert pm == "dnf"

    def test_returns_none_on_windows(self):
        with patch("platform.system", return_value="Windows"), \
             patch("shutil.which", return_value=None):
            pm = _detect_pm()
        assert pm is None

    def test_returns_none_when_no_pm_found(self):
        with patch("platform.system", return_value="Linux"), \
             patch("shutil.which", return_value=None):
            pm = _detect_pm()
        assert pm is None


# ---------------------------------------------------------------------------
# _install_hint
# ---------------------------------------------------------------------------

class TestInstallHint:
    def test_hint_contains_package_name(self):
        hint = _install_hint(["aria2c"], "apt")
        assert "aria2" in hint

    def test_hint_contains_pm_command(self):
        hint = _install_hint(["aria2c"], "apt")
        assert "apt-get" in hint

    def test_hint_brew_chntpw_includes_tap(self):
        hint = _install_hint(["chntpw"], "brew")
        assert "sidneys/homebrew" in hint

    def test_hint_no_pm_lists_binaries(self):
        hint = _install_hint(["aria2c", "wimlib-imagex"], None)
        assert "aria2c" in hint
        assert "wimlib-imagex" in hint

    def test_unknown_bin_falls_back_to_exe_name(self):
        hint = _install_hint(["sometool"], "apt")
        assert "sometool" in hint


# ---------------------------------------------------------------------------
# ensure_deps — all present
# ---------------------------------------------------------------------------

class TestEnsureDepsAllPresent:
    def test_no_exit_when_all_present(self):
        with patch("shutil.which", return_value="/usr/bin/tool"):
            # Should return silently without raising
            ensure_deps(["aria2c", "cabextract"], iso_alternatives={"genisoimage"})

    def test_does_not_call_install_when_all_present(self):
        with patch("shutil.which", return_value="/usr/bin/tool"), \
             patch("uup_builder.deps._install_hint") as mock_hint:
            ensure_deps(["aria2c"], iso_alternatives={"genisoimage"})
        mock_hint.assert_not_called()


# ---------------------------------------------------------------------------
# ensure_deps — missing binaries
# ---------------------------------------------------------------------------

class TestEnsureDepsMissing:
    def test_exits_when_binary_missing(self):
        with patch("shutil.which", return_value=None), \
             patch("uup_builder.deps._detect_pm", return_value="apt"):
            with pytest.raises(SystemExit):
                ensure_deps(["aria2c"], iso_alternatives={"genisoimage"})

    def test_exits_with_no_pm(self):
        with patch("shutil.which", return_value=None), \
             patch("uup_builder.deps._detect_pm", return_value=None):
            with pytest.raises(SystemExit):
                ensure_deps(["aria2c"], iso_alternatives={"genisoimage"})

    def test_exit_message_contains_missing_bin(self, capsys):
        with patch("shutil.which", return_value=None), \
             patch("uup_builder.deps._detect_pm", return_value="apt"), \
             patch("uup_builder.deps.bail", side_effect=SystemExit) as mock_bail:
            with pytest.raises(SystemExit):
                ensure_deps(["aria2c"], iso_alternatives={"genisoimage"})
        args = mock_bail.call_args[0][0]
        assert "aria2c" in args

    def test_exit_message_contains_install_command(self):
        with patch("shutil.which", return_value=None), \
             patch("uup_builder.deps._detect_pm", return_value="apt"), \
             patch("uup_builder.deps.bail", side_effect=SystemExit) as mock_bail:
            with pytest.raises(SystemExit):
                ensure_deps(["aria2c"], iso_alternatives={"genisoimage"})
        args = mock_bail.call_args[0][0]
        assert "apt-get" in args or "install" in args

    def test_missing_iso_tool_included_in_message(self):
        def _which(name):
            # All required bins present; no ISO tool present
            return "/usr/bin/tool" if name not in ("genisoimage", "mkisofs") else None

        with patch("shutil.which", side_effect=_which), \
             patch("uup_builder.deps._detect_pm", return_value="apt"), \
             patch("uup_builder.deps.bail", side_effect=SystemExit) as mock_bail:
            with pytest.raises(SystemExit):
                ensure_deps(["aria2c"], iso_alternatives={"genisoimage", "mkisofs"})
        args = mock_bail.call_args[0][0]
        assert "genisoimage" in args or "mkisofs" in args

    def test_no_install_attempt_is_made(self):
        """ensure_deps must never try to run any install subprocess."""
        with patch("shutil.which", return_value=None), \
             patch("uup_builder.deps._detect_pm", return_value="apt"), \
             patch("subprocess.run") as mock_run, \
             patch("uup_builder.deps.bail", side_effect=SystemExit):
            with pytest.raises(SystemExit):
                ensure_deps(["aria2c"], iso_alternatives={"genisoimage"})
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Package map completeness
# ---------------------------------------------------------------------------

class TestPkgMap:
    EXPECTED_BINS = ["aria2c", "cabextract", "wimlib-imagex", "chntpw", "genisoimage"]
    EXPECTED_PMS  = ["apt", "pacman", "dnf", "zypper", "brew"]

    def test_all_bins_have_apt_entry(self):
        for binary in self.EXPECTED_BINS:
            assert "apt" in _PKG_MAP.get(binary, {}), f"Missing apt entry for {binary}"

    def test_all_bins_have_brew_entry(self):
        for binary in self.EXPECTED_BINS:
            assert "brew" in _PKG_MAP.get(binary, {}), f"Missing brew entry for {binary}"

    def test_all_package_names_are_non_empty(self):
        for binary, pm_map in _PKG_MAP.items():
            for pm_name, pkg in pm_map.items():
                assert pkg, f"Empty package name for {binary} on {pm_name}"