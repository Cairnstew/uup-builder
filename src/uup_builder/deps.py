"""
uup_builder.deps
----------------
Checks that the binary dependencies required by the converter are present
on PATH and, if any are missing, prints clear manual-install instructions
and exits.

Supported package managers for install hints: apt, pacman, dnf, zypper, brew.
"""

from __future__ import annotations

import logging
import platform
import shutil
import sys
from typing import Optional

from uup_builder.output import bail, print_msg, HAS_RICH

__all__ = ["ensure_deps"]

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Package name mapping  { executable: { package_manager: package_name } }
# ---------------------------------------------------------------------------

_PKG_MAP: dict[str, dict[str, str]] = {
    "aria2c": {
        "apt":    "aria2",
        "pacman": "aria2",
        "dnf":    "aria2",
        "zypper": "aria2",
        "brew":   "aria2",
    },
    "cabextract": {
        "apt":    "cabextract",
        "pacman": "cabextract",
        "dnf":    "cabextract",
        "zypper": "cabextract",
        "brew":   "cabextract",
    },
    "wimlib-imagex": {
        "apt":    "wimtools",
        "pacman": "wimlib",
        "dnf":    "wimlib-utils",
        "zypper": "wimlib",
        "brew":   "wimlib",
    },
    "chntpw": {
        "apt":    "chntpw",
        "pacman": "chntpw",
        "dnf":    "chntpw",
        "zypper": "chntpw",
        "brew":   "chntpw",  # requires sidneys/homebrew or minacle/chntpw tap
    },
    "genisoimage": {
        "apt":    "genisoimage",
        "pacman": "cdrtools",
        "dnf":    "genisoimage",
        "zypper": "genisoimage",
        "brew":   "cdrtools",
    },
}

# genisoimage / mkisofs are alternatives — only one needs to be present
_ISO_ALTERNATIVES = {"genisoimage", "mkisofs"}


# ---------------------------------------------------------------------------
# Package manager detection (used only to tailor the hint message)
# ---------------------------------------------------------------------------

def _detect_pm() -> Optional[str]:
    """Return the name of the detected package manager, or None."""
    system = platform.system()
    if system == "Darwin":
        return "brew" if shutil.which("brew") else None
    if system == "Linux":
        for pm in ("apt-get", "pacman", "dnf", "zypper"):
            if shutil.which(pm):
                # normalise apt-get → apt for the hint lookup
                return "apt" if pm == "apt-get" else pm
    return None


def _install_hint(missing_bins: list[str], pm: Optional[str]) -> str:
    """Build a human-readable install command for the missing binaries."""
    if pm is None:
        pkg_names = [
            _PKG_MAP.get(b, {}).get("apt", b)   # fall back to the exe name itself
            for b in missing_bins
        ]
        return (
            "No supported package manager detected.\n"
            "Please install the following tools manually:\n"
            + "\n".join(f"  • {b}" for b in missing_bins)
        )

    pkg_names: list[str] = []
    for exe in missing_bins:
        pkg = _PKG_MAP.get(exe, {}).get(pm)
        pkg_names.append(pkg if pkg else exe)

    pm_cmds = {
        "apt":    f"sudo apt-get install -y {' '.join(pkg_names)}",
        "pacman": f"sudo pacman -S --noconfirm {' '.join(pkg_names)}",
        "dnf":    f"sudo dnf install -y {' '.join(pkg_names)}",
        "zypper": f"sudo zypper install -y {' '.join(pkg_names)}",
        "brew":   f"brew install {' '.join(pkg_names)}",
    }

    extra = ""
    if pm == "brew" and "chntpw" in missing_bins:
        extra = "\n  (chntpw also requires: brew tap sidneys/homebrew)"

    return f"Run:{extra}\n  {pm_cmds[pm]}"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def ensure_deps(
    required_bins: list[str],
    iso_alternatives: set[str] = _ISO_ALTERNATIVES,
) -> None:
    """
    Verify every binary in *required_bins* is on PATH.
    For ISO tools, at least one of *iso_alternatives* must be present.

    If anything is missing, print a clear message with the install command
    for the detected package manager, then exit.

    Parameters
    ----------
    required_bins:
        List of executable names that must all be present.
    iso_alternatives:
        Set of executable names where *any one* being present is sufficient.
    """
    missing_bins: list[str] = [b for b in required_bins if not shutil.which(b)]

    iso_ok = any(shutil.which(b) for b in iso_alternatives)
    if not iso_ok:
        missing_bins.append(next(iter(iso_alternatives)))

    if not missing_bins:
        log.debug("All dependencies satisfied.")
        return

    pm = _detect_pm()
    hint = _install_hint(missing_bins, pm)

    bail(
        f"Missing required tools: {', '.join(missing_bins)}\n\n"
        f"{hint}\n\n"
        "Once installed, re-run uup_builder."
    )