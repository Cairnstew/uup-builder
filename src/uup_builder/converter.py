"""
uup_builder.converter
---------------------
Downloads and runs the official uup-dump/converter ``convert.sh`` script.

The script is fetched from https://git.uupdump.net/uup-dump/converter on
first use and cached locally. Running it requires these system binaries:
    aria2c, cabextract, wimlib-imagex, chntpw, genisoimage (or mkisofs)

If any binaries are missing, uup_builder will print install instructions
and exit rather than attempting to install them automatically.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import requests

from uup_builder.deps import ensure_deps
from uup_builder.output import bail, print_info, print_ok

__all__ = ["Converter"]

log = logging.getLogger(__name__)

CONVERT_SH_URL = (
    "https://git.uupdump.net/uup-dump/converter/raw/branch/master/convert.sh"
)
CONVERT_VE_PLUGIN_URL = (
    "https://git.uupdump.net/uup-dump/converter/raw/branch/master/convert_ve_plugin"
)

_REQUIRED_BINS = ["aria2c", "cabextract", "wimlib-imagex", "chntpw"]
_ISO_BINS      = ["genisoimage", "mkisofs"]

_DEFAULT_CACHE = Path.home() / ".cache" / "uup-builder" / "converter"


class Converter:
    """
    Fetches and runs the official uup-dump ``convert.sh`` script.

    Parameters
    ----------
    compress:
        ``"wim"`` (default) or ``"esd"``.
    virtual_editions:
        Pass ``1`` as the third argument to ``convert.sh`` to create
        virtual editions (requires the ``convert_ve_plugin``).
    cache_dir:
        Where to cache the downloaded ``convert.sh``.
        Defaults to ``~/.cache/uup-builder/converter``.
    """

    def __init__(
        self,
        compress: str = "wim",
        virtual_editions: bool = False,
        cache_dir: Optional[str | Path] = None,
    ) -> None:
        if compress not in ("wim", "esd"):
            bail(f"Invalid compression type '{compress}'. Use 'wim' or 'esd'.")
        self.compress = compress
        self.virtual_editions = virtual_editions
        self.cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_deps(self) -> list[str]:
        """Return a list of missing system dependency names (empty = all OK)."""
        missing = [b for b in _REQUIRED_BINS if not shutil.which(b)]
        if not any(shutil.which(b) for b in _ISO_BINS):
            missing.append("genisoimage or mkisofs")
        return missing

    def ensure_script(self, force: bool = False) -> Path:
        """
        Download ``convert.sh`` into ``cache_dir`` if not already present.

        Parameters
        ----------
        force:
            Re-download even if the script already exists.

        Returns
        -------
        Path
            Absolute path to the cached ``convert.sh``.
        """
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        script = self.cache_dir / "convert.sh"

        if script.exists() and not force:
            log.debug("Using cached convert.sh: %s", script)
            return script

        print_info(f"Downloading convert.sh from {CONVERT_SH_URL} …")
        try:
            r = requests.get(CONVERT_SH_URL, timeout=30)
            r.raise_for_status()
        except requests.RequestException as exc:
            bail(f"Failed to download convert.sh: {exc}")

        script.write_bytes(r.content)
        script.chmod(0o755)
        log.debug("Saved convert.sh (%d bytes) to %s", len(r.content), script)

        # Also fetch the virtual editions plugin (best-effort, no error if missing)
        plugin = self.cache_dir / "convert_ve_plugin"
        try:
            rp = requests.get(CONVERT_VE_PLUGIN_URL, timeout=30)
            if rp.ok:
                plugin.write_bytes(rp.content)
                plugin.chmod(0o755)
                log.debug("Saved convert_ve_plugin to %s", plugin)
        except requests.RequestException:
            log.debug("Could not download convert_ve_plugin (optional)")

        print_ok("convert.sh ready.")
        return script

    def convert(
        self,
        uup_dir: str | Path,
        iso_out: Optional[str | Path] = None,
        update_script: bool = False,
    ) -> None:
        """
        Convert UUP files in *uup_dir* to a bootable ISO by running ``convert.sh``.

        Missing system dependencies cause an immediate exit with install
        instructions rather than any automatic installation attempt.

        Parameters
        ----------
        uup_dir:
            Directory containing downloaded UUP files.
        iso_out:
            Ignored — ``convert.sh`` names the ISO automatically based on
            the build metadata and places it in the current working directory.
        update_script:
            If ``True``, re-download ``convert.sh`` before running.
        """
        if sys.platform == "win32":
            bail("convert.sh requires a Unix-like environment (Linux or macOS).")

        uup_dir = Path(uup_dir).resolve()
        if not uup_dir.is_dir():
            bail(f"UUP directory not found: {uup_dir}")

        # Check deps — exits with install instructions if anything is missing.
        ensure_deps(_REQUIRED_BINS, set(_ISO_BINS))

        script = self.ensure_script(force=update_script)

        import tempfile
        import shutil as _shutil

        cwd = Path.cwd()
        with tempfile.TemporaryDirectory(prefix="uup_convert_") as run_dir:
            run_dir = Path(run_dir)
            for name in ("convert.sh", "convert_ve_plugin",
                         "convert_config_linux", "convert_config_macos"):
                src = self.cache_dir / name
                if src.exists():
                    _shutil.copy2(src, run_dir / name)
                    (run_dir / name).chmod(0o755)

            cmd = [
                "bash", str(run_dir / "convert.sh"),
                self.compress,
                str(uup_dir),
                "1" if self.virtual_editions else "0",
            ]

            print_info(f"Running convert.sh (ISO will be written to {cwd})")
            result = subprocess.run(cmd, cwd=str(cwd))

        if result.returncode != 0:
            bail(f"convert.sh exited with code {result.returncode}")

        print_ok(f"ISO build complete! Check {cwd} for the output .iso file.")