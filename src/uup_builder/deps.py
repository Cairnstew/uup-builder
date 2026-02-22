"""
uup_builder.deps
----------------
Detects the system package manager and auto-installs any missing
binary dependencies required by the converter.

Supported package managers: apt, pacman, dnf, zypper, brew.
macOS Homebrew tap ``sidneys/homebrew`` is added automatically for chntpw.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

from uup_builder.output import bail, print_info, print_ok, print_msg, HAS_RICH

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
        "brew":   "chntpw",           # requires sidneys/homebrew or minacle/chntpw tap
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
# Package manager detection
# ---------------------------------------------------------------------------

@dataclass
class _PackageManager:
    name: str
    install_cmd: list[str]          # base install command (without package names)
    update_cmd:  Optional[list[str]] = None   # update index before installing
    sudo: bool = True               # prepend sudo?
    extra_setup: list[list[str]] = field(default_factory=list)  # extra commands to run first


def _detect_pm() -> Optional[_PackageManager]:
    system = platform.system()

    if system == "Darwin":
        if shutil.which("brew"):
            return _PackageManager(
                name="brew",
                install_cmd=["brew", "install"],
                sudo=False,
                extra_setup=[
                    # tap needed for chntpw on Intel Macs
                    ["brew", "tap", "sidneys/homebrew"],
                ],
            )
        return None

    if system == "Linux":
        if shutil.which("apt-get"):
            return _PackageManager(
                name="apt",
                install_cmd=["apt-get", "install", "-y"],
                update_cmd=["apt-get", "update", "-y"],
                sudo=True,
            )
        if shutil.which("pacman"):
            return _PackageManager(
                name="pacman",
                install_cmd=["pacman", "-S", "--noconfirm"],
                update_cmd=["pacman", "-Sy"],
                sudo=True,
            )
        if shutil.which("dnf"):
            return _PackageManager(
                name="dnf",
                install_cmd=["dnf", "install", "-y"],
                sudo=True,
            )
        if shutil.which("zypper"):
            return _PackageManager(
                name="zypper",
                install_cmd=["zypper", "install", "-y"],
                sudo=True,
            )

    return None


# ---------------------------------------------------------------------------
# Install helpers
# ---------------------------------------------------------------------------

def _prepend_sudo(cmd: list[str], use_sudo: bool) -> list[str]:
    if use_sudo and shutil.which("sudo"):
        return ["sudo"] + cmd
    return cmd


def _run_install(cmd: list[str]) -> None:
    log.debug("$ %s", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        bail(f"Installation command failed (exit {result.returncode}): {' '.join(cmd)}")


def _install_packages(pm: _PackageManager, packages: list[str]) -> None:
    # Run any extra setup steps (e.g. brew tap)
    for extra in pm.extra_setup:
        log.debug("Extra setup: %s", " ".join(extra))
        subprocess.run(extra, check=False)

    # Update package index
    if pm.update_cmd:
        print_info(f"Updating package index ({pm.name})…")
        _run_install(_prepend_sudo(pm.update_cmd, pm.sudo))

    # Install
    cmd = _prepend_sudo(pm.install_cmd + packages, pm.sudo)
    print_info(f"Installing: {' '.join(packages)}")
    _run_install(cmd)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def ensure_deps(required_bins: list[str], iso_alternatives: set[str] = _ISO_ALTERNATIVES) -> None:
    """
    Check that every binary in *required_bins* is on PATH.
    For ISO tools, at least one of *iso_alternatives* must be present.

    Any missing tools are installed automatically using the detected
    system package manager.  Exits with an error if no supported package
    manager is found.

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
        # Pick the first iso alternative as the one to install
        missing_bins.append(next(iter(iso_alternatives)))

    if not missing_bins:
        log.debug("All dependencies satisfied.")
        return

    _warn(f"Missing dependencies: {', '.join(missing_bins)}")

    pm = _detect_pm()
    if pm is None:
        bail(
            "Could not detect a supported package manager "
            "(apt, pacman, dnf, zypper, brew).\n"
            "Please install the following manually and re-run:\n"
            + "\n".join(f"  • {b}" for b in missing_bins)
        )

    # Resolve executable names → package names for this package manager
    packages_to_install: list[str] = []
    for exe in missing_bins:
        pkg_name = _PKG_MAP.get(exe, {}).get(pm.name)
        if pkg_name is None:
            bail(
                f"No known package name for '{exe}' on {pm.name}. "
                "Please install it manually."
            )
        if pkg_name not in packages_to_install:
            packages_to_install.append(pkg_name)

    _install_packages(pm, packages_to_install)

    # Verify everything is now available
    still_missing = [b for b in missing_bins if not shutil.which(b)]
    # Re-check ISO tools too
    if not any(shutil.which(b) for b in iso_alternatives):
        still_missing.append(f"one of: {', '.join(iso_alternatives)}")

    if still_missing:
        bail(
            "Installation appeared to succeed but these tools are still not found: "
            + ", ".join(still_missing)
            + "\nTry installing them manually."
        )

    print_ok("All dependencies installed.")


def _warn(msg: str) -> None:
    if HAS_RICH:
        print_msg(f"[yellow]⚠[/yellow] {msg}")
    else:
        print(f"⚠ {msg}")