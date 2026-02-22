"""
Tests for uup_builder.deps
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, call

import pytest

for mod in ("uup_dump_api", "uup_dump_api.adapter", "uup_dump_api.exceptions"):
    sys.modules.setdefault(mod, MagicMock())

from uup_builder.deps import ensure_deps, _detect_pm, _PKG_MAP  # noqa: E402


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

        assert pm is not None
        assert pm.name == "apt"

    def test_detects_brew_on_macos(self):
        def _which(name):
            return "/opt/homebrew/bin/brew" if name == "brew" else None

        with patch("platform.system", return_value="Darwin"), \
             patch("shutil.which", side_effect=_which):
            pm = _detect_pm()

        assert pm is not None
        assert pm.name == "brew"
        assert pm.sudo is False

    def test_detects_pacman(self):
        def _which(name):
            return "/usr/bin/pacman" if name == "pacman" else None

        with patch("platform.system", return_value="Linux"), \
             patch("shutil.which", side_effect=_which):
            pm = _detect_pm()

        assert pm is not None
        assert pm.name == "pacman"

    def test_detects_dnf(self):
        def _which(name):
            return "/usr/bin/dnf" if name == "dnf" else None

        with patch("platform.system", return_value="Linux"), \
             patch("shutil.which", side_effect=_which):
            pm = _detect_pm()

        assert pm is not None
        assert pm.name == "dnf"

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
# ensure_deps — all present
# ---------------------------------------------------------------------------

class TestEnsureDepsAllPresent:
    def test_no_install_when_all_present(self):
        with patch("shutil.which", return_value="/usr/bin/tool"):
            # Should not raise or call install
            with patch("uup_builder.deps._install_packages") as mock_install:
                ensure_deps(["aria2c", "cabextract"], iso_alternatives={"genisoimage"})
            mock_install.assert_not_called()


# ---------------------------------------------------------------------------
# ensure_deps — missing binaries
# ---------------------------------------------------------------------------

class TestEnsureDepsMissing:
    def test_missing_binary_triggers_install(self):
        def _which(name):
            # Only genisoimage (iso alt) is present; aria2c is missing
            return "/usr/bin/genisoimage" if name == "genisoimage" else None

        # Fake an apt PM
        from uup_builder.deps import _PackageManager
        fake_pm = _PackageManager(
            name="apt",
            install_cmd=["apt-get", "install", "-y"],
            sudo=False,
        )

        with patch("shutil.which", side_effect=_which), \
             patch("uup_builder.deps._detect_pm", return_value=fake_pm), \
             patch("uup_builder.deps._install_packages") as mock_install, \
             patch("uup_builder.deps._prepend_sudo", side_effect=lambda cmd, _: cmd):

            # After "install", pretend aria2c is now available
            call_count = {"n": 0}
            original_which = _which

            def _which_after(name):
                call_count["n"] += 1
                # After install_packages is called, everything is available
                if mock_install.called:
                    return f"/usr/bin/{name}"
                return original_which(name)

            with patch("shutil.which", side_effect=_which_after):
                ensure_deps(["aria2c"], iso_alternatives={"genisoimage"})

        mock_install.assert_called_once()

    def test_no_pm_found_exits(self):
        with patch("shutil.which", return_value=None), \
             patch("uup_builder.deps._detect_pm", return_value=None):
            with pytest.raises(SystemExit):
                ensure_deps(["aria2c"], iso_alternatives={"genisoimage"})

    def test_unknown_package_for_pm_exits(self):
        from uup_builder.deps import _PackageManager
        fake_pm = _PackageManager(
            name="apt",
            install_cmd=["apt-get", "install", "-y"],
            sudo=False,
        )

        with patch("shutil.which", return_value=None), \
             patch("uup_builder.deps._detect_pm", return_value=fake_pm):
            # "unknowntool" has no mapping in _PKG_MAP
            with pytest.raises(SystemExit):
                ensure_deps(["unknowntool"], iso_alternatives={"genisoimage"})


# ---------------------------------------------------------------------------
# Package map completeness
# ---------------------------------------------------------------------------

class TestPkgMap:
    EXPECTED_BINS = ["aria2c", "cabextract", "wimlib-imagex", "chntpw", "genisoimage"]
    EXPECTED_PMS = ["apt", "pacman", "dnf", "zypper", "brew"]

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