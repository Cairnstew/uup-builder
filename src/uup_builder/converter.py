"""
uup_builder.converter
---------------------
Pure-Python reimplementation of the uup-dump/converter ``convert.sh`` script.

Requires the same system binaries as the original shell script:
    aria2c, cabextract, wimlib-imagex, chntpw, genisoimage (or mkisofs)

These are thin wrappers — Python orchestrates the same sequence of external
tool calls that the bash script did, so the output ISO is identical.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from uup_builder.output import HAS_RICH, bail, print_info, print_msg, print_ok
from uup_builder.deps import ensure_deps

__all__ = ["Converter"]

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Edition names recognised as metadata ESDs  (from convert.sh $editions list)
# ---------------------------------------------------------------------------
_EDITIONS = {
    "analogonecore", "andromeda", "cloud", "cloude", "clouden", "cloudn",
    "cloudedition", "cloudeditionn", "core", "corecountryspecific", "coren",
    "coresinglelanguage", "coresystemserver", "education", "educationn",
    "embedded", "embeddede", "embeddedeeval", "embeddedeval", "enterprise",
    "enterpriseeval", "enterpriseg", "enterprisegn", "enterprisen",
    "enterpriseneval", "enterprises", "enterpriseseval", "enterprisesn",
    "enterprisesneval", "holographic", "hubos", "iotenterprise",
    "iotenterprisek", "iotenterprises", "iotenterprisesk", "iotos", "iotuap",
    "lite", "mobilecore", "onecoreupdateos", "ppipro", "professional",
    "professionalcountryspecific", "professionaleducation",
    "professionaleducationn", "professionaln", "professionalsinglelanguage",
    "professionalworkstation", "professionalworkstationn", "serverarm64",
    "serverarm64core", "serverazurecor", "serverazurecorcore",
    "serverazurenano", "serverazurenanocore", "serverazurestackhcicor",
    "servercloudstorage", "servercloudstoragecore", "serverdatacenter",
    "serverdatacenteracor", "serverdatacenteracorcore", "serverdatacentercor",
    "serverdatacentercorcore", "serverdatacentercore", "serverdatacentereval",
    "serverdatacenterevalcor", "serverdatacenterevalcorcore",
    "serverdatacenterevalcore", "serverdatacenternano",
    "serverdatacenternanocore", "serverhypercore", "serverrdsh",
    "serverrdshcore", "serversolution", "serversolutioncore", "serverstandard",
    "serverstandardacor", "serverstandardacorcore", "serverstandardcor",
    "serverstandardcorcore", "serverstandardcore", "serverstandardeval",
    "serverstandardevalcor", "serverstandardevalcorcore",
    "serverstandardevalcore", "serverstandardnano", "serverstandardnanocore",
    "serverstoragestandard", "serverstoragestandardcore",
    "serverstoragestandardeval", "serverstoragestandardevalcore",
    "serverstorageworkgroup", "serverstorageworkgroupcore",
    "serverstorageworkgroupeval", "serverstorageworkgroupevalcore",
    "serverturbine", "serverturbinecor", "serverweb", "serverwebcore",
    "starter", "startern", "wnc",
}

# Metadata ESD pattern — UUP dump names them:  MetadataESD_<edition>_<lang>.esd
# e.g.  MetadataESD_professional_en-us.esd
_METADATA_RE = re.compile(
    r"^(" + "|".join(re.escape(e) for e in _EDITIONS) + r")_[a-z]{2}-[a-z]+\.esd$",
    re.IGNORECASE,
)

# Required system binaries
_REQUIRED_BINS = ["aria2c", "cabextract", "wimlib-imagex", "chntpw"]
_ISO_BINS      = ["genisoimage", "mkisofs"]

# chntpw script to patch the setup registry hive
_CHNTPW_SCRIPT = """\
cd Microsoft\\Windows NT\\CurrentVersion
nv 1 SystemRoot
ed SystemRoot
X:\\$Windows.~bt\\Windows
cd WinPE
nv 1 InstRoot
ed InstRoot
X:\\$Windows.~bt
q
y
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(*args: str, check: bool = True, capture: bool = False, **kwargs) -> subprocess.CompletedProcess:
    """Run a command, logging it at DEBUG level."""
    log.debug("$ %s", " ".join(str(a) for a in args))
    return subprocess.run(
        list(args),
        check=check,
        capture_output=capture,
        text=capture,
        **kwargs,
    )


def _wiminfo(path: Path, index: int) -> dict[str, str]:
    """
    Return a dict of ``Key: Value`` pairs from ``wimlib-imagex info <path> <index>``.
    """
    result = _run("wimlib-imagex", "info", str(path), str(index),
                  capture=True, check=False)
    out: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            out[key.strip()] = val.strip()
    return out


def _find_iso_tool() -> str:
    for tool in _ISO_BINS:
        if shutil.which(tool):
            return tool
    bail("Neither genisoimage nor mkisofs is installed. "
         "Install one to create the ISO image.")


def _check_deps() -> list[str]:
    """Return missing binary names. Kept for programmatic use; convert() auto-installs."""
    missing = [b for b in _REQUIRED_BINS if not shutil.which(b)]
    if not any(shutil.which(b) for b in _ISO_BINS):
        missing.append("genisoimage or mkisofs")
    return missing


# ---------------------------------------------------------------------------
# Main Converter class
# ---------------------------------------------------------------------------

class Converter:
    """
    Pure-Python reimplementation of the uup-dump ``convert.sh`` script.

    Orchestrates ``cabextract``, ``wimlib-imagex``, ``chntpw``, and
    ``genisoimage`` / ``mkisofs`` to build a bootable Windows ISO from a
    directory of downloaded UUP files.

    Parameters
    ----------
    compress:
        ``"wim"`` (default) — standard compression (``--compress=maximum``)
        ``"esd"`` — solid ESD compression (``--solid``)
    virtual_editions:
        If ``True``, attempt to create virtual editions (requires
        ``convert_ve_plugin`` — same limitation as the shell script).
    work_dir:
        Scratch directory for intermediate files. Uses a system temp dir
        if not specified; the directory is cleaned up after conversion.
    """

    def __init__(
        self,
        compress: str = "wim",
        virtual_editions: bool = False,
        work_dir: Optional[str | Path] = None,
    ) -> None:
        if compress not in ("wim", "esd"):
            bail(f"Invalid compression type '{compress}'. Use 'wim' or 'esd'.")
        self.compress = compress
        self.virtual_editions = virtual_editions
        self._work_dir = Path(work_dir) if work_dir else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_deps(self) -> list[str]:
        """Return a list of missing system dependency names (empty = all OK)."""
        return _check_deps()

    def install_deps(self) -> None:
        """Explicitly install any missing system dependencies."""
        ensure_deps(_REQUIRED_BINS, set(_ISO_BINS))

    def convert(
        self,
        uup_dir: str | Path,
        iso_out: Optional[str | Path] = None,
    ) -> Path:
        """
        Convert the UUP files in *uup_dir* to a bootable ISO.

        Parameters
        ----------
        uup_dir:
            Directory containing downloaded UUP ``.esd`` / ``.cab`` files.
        iso_out:
            Explicit output path for the ISO. If omitted the ISO is created
            in the current working directory using the same naming convention
            as the original shell script (``BUILD.SPBUILD_EDITION_ARCH_LANG.iso``).

        Returns
        -------
        Path
            Absolute path to the produced ISO file.
        """
        uup_dir = Path(uup_dir).resolve()
        if not uup_dir.is_dir():
            bail(f"UUP directory not found: {uup_dir}")

        ensure_deps(_REQUIRED_BINS, set(_ISO_BINS))

        iso_tool = _find_iso_tool()

        # Use caller-supplied or auto-created temp directory
        if self._work_dir:
            self._work_dir.mkdir(parents=True, exist_ok=True)
            return self._run_conversion(uup_dir, iso_out, iso_tool, self._work_dir)
        else:
            with tempfile.TemporaryDirectory(prefix="uup_builder_") as td:
                return self._run_conversion(uup_dir, iso_out, iso_tool, Path(td))

    # ------------------------------------------------------------------
    # Conversion pipeline  (mirrors convert.sh top-to-bottom)
    # ------------------------------------------------------------------

    def _run_conversion(
        self,
        uup_dir: Path,
        iso_out: Optional[str | Path],
        iso_tool: str,
        temp_dir: Path,
    ) -> Path:

        iso_dir  = Path.cwd() / "ISODIR"
        iso_dir.mkdir(exist_ok=True)

        try:
            iso_path = self._pipeline(uup_dir, iso_out, iso_tool, temp_dir, iso_dir)
        finally:
            self._cleanup(iso_dir, temp_dir)

        return iso_path

    def _pipeline(
        self,
        uup_dir: Path,
        iso_out: Optional[str | Path],
        iso_tool: str,
        temp_dir: Path,
        iso_dir: Path,
    ) -> Path:

        # ----------------------------------------------------------------
        # 1. Find metadata ESDs
        # ----------------------------------------------------------------
        print_info("Scanning for metadata ESDs…")
        metadata_files = sorted(
            f for f in uup_dir.iterdir()
            if f.is_file() and _METADATA_RE.match(f.name)
        )
        if not metadata_files:
            bail(f"No metadata ESDs found in {uup_dir}.")

        # ----------------------------------------------------------------
        # 2. Detect language from first metadata ESD
        # ----------------------------------------------------------------
        first_meta = metadata_files[0]
        info3 = _wiminfo(first_meta, 3)
        lang = info3.get("Default Language", "")
        if not lang:
            bail("Could not determine language from metadata ESD.")

        # Filter metadata files to those matching our language
        metadata_files = sorted(
            f for f in metadata_files
            if lang.lower() in f.name.lower()
        )
        first_meta = metadata_files[0]
        log.debug("Language: %s  |  %d metadata ESD(s)", lang, len(metadata_files))

        # Warn if updates (.cab patches) are present
        update_cabs = list(uup_dir.glob("*windows1*-kb*.cab")) + list(uup_dir.glob("ssu-*.cab"))
        if update_cabs:
            _warn("This converter cannot integrate cumulative updates. "
                  "Use the Windows version of the converter for that.")

        # ----------------------------------------------------------------
        # 3. Convert .cab packages → .esd
        # ----------------------------------------------------------------
        extra_esds: list[Path] = []
        for cab in uup_dir.iterdir():
            # UUP dump prefixes convertible cabs with "cabs_"
            # Skip update cabs, aggregated metadata, desktop deployment, etc.
            if not (cab.suffix.lower() == ".cab" and cab.name.startswith("cabs_")):
                continue

            stem = cab.stem
            print_info(f"CAB → ESD: {stem}")
            extract_dir = temp_dir / "cab_extract"
            extract_dir.mkdir(exist_ok=True)

            _run("cabextract", "-d", str(extract_dir), str(cab))
            esd_path = temp_dir / f"{stem}.esd"
            _run("wimlib-imagex", "capture", str(extract_dir), str(esd_path),
                 "--no-acls", "--norpfix", "Edition Package", "Edition Package")
            shutil.rmtree(extract_dir, ignore_errors=True)
            extra_esds.append(esd_path)

        # ----------------------------------------------------------------
        # 4. Create ISO directory structure from metadata ESD index 1
        # ----------------------------------------------------------------
        print_info("Creating ISO directory structure…")
        os.environ["WIMLIB_IMAGEX_IGNORE_CASE"] = "1"
        _run("wimlib-imagex", "apply", str(first_meta), "1", str(iso_dir),
             "--no-acls", "--no-attributes")

        # ----------------------------------------------------------------
        # 5. Export winre.wim from index 2
        # ----------------------------------------------------------------
        print_info("Exporting winre.wim…")
        winre_wim = temp_dir / "winre.wim"
        _run("wimlib-imagex", "export", str(first_meta), "2", str(winre_wim),
             "--compress=maximum", "--boot")

        # ----------------------------------------------------------------
        # 6. Build boot.wim
        # ----------------------------------------------------------------
        self._build_boot_wim(first_meta, winre_wim, iso_dir, temp_dir)

        # ----------------------------------------------------------------
        # 7. Extract xmllite.dll for setup
        # ----------------------------------------------------------------
        _run("wimlib-imagex", "extract", str(first_meta), "3",
             "/Windows/System32/xmllite.dll",
             "--no-acls", f"--dest-dir={iso_dir / 'sources'}")

        # ----------------------------------------------------------------
        # 8. Export each edition into install.<type>
        # ----------------------------------------------------------------
        ref_esds = list(uup_dir.glob("*.[eE][sS][dD]")) + extra_esds
        install_wim = iso_dir / "sources" / f"install.{self.compress}"
        indexes_exported = 0

        for meta in metadata_files:
            info = _wiminfo(meta, 3)
            edition_id    = info.get("Edition ID", "")
            edition_name  = info.get("Name", "")
            install_type  = info.get("Installation Type", "")

            # Rename Server Core variants to match the shell script logic
            if install_type == "Server Core":
                if edition_id == "ServerStandard":
                    edition_id = "ServerStandardCore"
                elif edition_id == "ServerDatacenter":
                    edition_id = "ServerDatacenterCore"
                elif edition_id == "ServerTurbine":
                    edition_id = "ServerTurbineCore"

            display_name = self._make_display_name(edition_id, edition_name)
            print_info(f"Exporting {display_name} → install.{self.compress}…")

            ref_args = ["--ref=" + str(p) for p in ref_esds if str(p) != str(meta)]
            compress_flag = "--solid" if self.compress == "esd" else "--compress=maximum"

            _run("wimlib-imagex", "export", str(meta), "3",
                 str(install_wim), display_name, compress_flag, *ref_args)

            indexes_exported += 1

            # Set FLAGS property on the exported image
            _run("wimlib-imagex", "info", str(install_wim),
                 str(indexes_exported), "--image-property", f"FLAGS={edition_id}")

            # Embed winre.wim into each install image
            print_info(f"Adding winre.wim to {display_name}…")
            _run("wimlib-imagex", "update", str(install_wim),
                 str(indexes_exported),
                 "--command",
                 f"add {winre_wim} /Windows/System32/Recovery/winre.wim")

        # ----------------------------------------------------------------
        # 9. Determine ISO metadata (build, arch, label, filename)
        # ----------------------------------------------------------------
        info   = _wiminfo(first_meta, 3)
        build  = info.get("Build", "0")
        spbuild = info.get("Service Pack Build", "0")
        arch   = info.get("Architecture", "amd64")
        if arch == "x86_64":
            arch = "x64"

        if indexes_exported > 1:
            edition_label = "MULTI"
        else:
            edition_label = info.get("Edition ID", "UNKNOWN")

        iso_label = f"{build}.{spbuild}_{arch}_{lang}".upper()
        auto_name = f"{build}.{spbuild}_{edition_label}_{arch}_{lang}.iso".upper()

        # ----------------------------------------------------------------
        # 10. Copy boot fonts for newer builds (>= 18890)
        # ----------------------------------------------------------------
        if int(build) >= 18890:
            boot_fonts_src = iso_dir / "boot" / "Fonts"
            if boot_fonts_src.is_dir():
                boot_fonts_dst      = iso_dir / "boot" / "fonts"
                efi_fonts_dst       = iso_dir / "efi" / "microsoft" / "boot" / "fonts"
                boot_fonts_dst.mkdir(parents=True, exist_ok=True)
                efi_fonts_dst.mkdir(parents=True, exist_ok=True)
                same_dir = (
                    str(boot_fonts_src.resolve()).lower() ==
                    str(boot_fonts_dst.resolve()).lower()
                )
                for font in boot_fonts_src.iterdir():
                    dst_boot = boot_fonts_dst / font.name
                    if not same_dir:
                        shutil.copy2(font, dst_boot)
                    dst_efi = efi_fonts_dst / font.name
                    if str(font.resolve()).lower() != str(dst_efi.resolve()).lower():
                        shutil.copy2(font, dst_efi)
                if not same_dir:
                    shutil.rmtree(boot_fonts_src)

                _run("wimlib-imagex", "extract", str(first_meta), "3",
                     "/Windows/Boot/Fonts",
                     "--no-acls", f"--dest-dir={iso_dir / 'boot'}")

        # ----------------------------------------------------------------
        # 11. Optimise install image if virtual editions were added
        #     (virtual edition support is a no-op here — same as original
        #      when the plugin is absent)
        # ----------------------------------------------------------------
        if self.virtual_editions:
            _warn("Virtual editions require the convert_ve_plugin — skipping.")

        # ----------------------------------------------------------------
        # 12. Create the ISO
        # ----------------------------------------------------------------
        out_path = Path(iso_out).resolve() if iso_out else Path.cwd() / auto_name
        if out_path.exists():
            out_path.unlink()

        print_info(f"Creating ISO image: {out_path.name}  (label: {iso_label})")

        # Touch all files so timestamps are consistent
        for p in iso_dir.rglob("*"):
            try:
                os.utime(p, None)
            except OSError:
                pass

        if arch == "arm64":
            _run(iso_tool,
                 "-b", "efi/microsoft/boot/efisys.bin",
                 "--no-emul-boot",
                 "--udf", "-iso-level", "3",
                 "--hide", "*",
                 "-allow-limited-size",
                 "-V", iso_label,
                 "-o", str(out_path),
                 str(iso_dir))
        else:
            _run(iso_tool,
                 "-b", "boot/etfsboot.com",
                 "--no-emul-boot",
                 "--eltorito-alt-boot",
                 "-b", "efi/microsoft/boot/efisys.bin",
                 "--no-emul-boot",
                 "--udf", "-iso-level", "3",
                 "--hide", "*",
                 "-allow-limited-size",
                 "-V", iso_label,
                 "-o", str(out_path),
                 str(iso_dir))

        print_ok(f"Done — ISO written to {out_path}")
        return out_path

    # ------------------------------------------------------------------
    # boot.wim construction  (step 6 of the pipeline)
    # ------------------------------------------------------------------

    def _build_boot_wim(
        self,
        first_meta: Path,
        winre_wim: Path,
        iso_dir: Path,
        temp_dir: Path,
    ) -> None:
        print_info("Building boot.wim…")
        boot_wim = iso_dir / "sources" / "boot.wim"

        # Start with winre.wim as the first image
        shutil.copy2(winre_wim, boot_wim)

        # Rename first image
        _run("wimlib-imagex", "info", str(boot_wim), "1",
             "Microsoft Windows PE", "Microsoft Windows PE",
             "--image-property", "FLAGS=9")

        # Extract SOFTWARE hive from boot.wim index 1
        sw_hive = temp_dir / "SOFTWARE"
        _run("wimlib-imagex", "extract", str(boot_wim), "1",
             "--dest-dir", str(temp_dir),
             "/Windows/System32/config/SOFTWARE",
             "--no-acls")

        # Patch the hive with chntpw
        chntpw_proc = subprocess.run(
            ["chntpw", "-e", str(sw_hive)],
            input=_CHNTPW_SCRIPT,
            capture_output=True,
            text=True,
        )
        log.debug("chntpw stdout: %s", chntpw_proc.stdout)

        # Put patched hive back
        _run("wimlib-imagex", "update", str(boot_wim), "1",
             "--command", f"add {sw_hive} /Windows/System32/config/SOFTWARE")

        # Extract winpe.jpg if present (ignore error if missing)
        _run("wimlib-imagex", "extract", str(boot_wim), "1",
             "/Windows/System32/winpe.jpg",
             "--no-acls", f"--dest-dir={iso_dir / 'sources'}",
             check=False)

        # Pick background image
        bckimg = self._find_background(iso_dir)

        # Add background into index 1
        for dest in ("/Windows/system32/setup.bmp",
                     "/Windows/system32/winpe.jpg",
                     "/Windows/system32/winre.jpg"):
            _run("wimlib-imagex", "update", str(boot_wim), "1",
                 "--command", f"add {iso_dir / 'sources' / bckimg} {dest}")

        # Remove winpeshl.ini from index 1
        _run("wimlib-imagex", "update", str(boot_wim), "1",
             "--command", "delete /Windows/System32/winpeshl.ini",
             check=False)

        # Export winre as second image ("Microsoft Windows Setup")
        _run("wimlib-imagex", "export", str(winre_wim), "1",
             str(boot_wim),
             "Microsoft Windows Setup", "Microsoft Windows Setup")

        # Collect boot sources from ISODIR/sources
        update_cmds: list[str] = []
        update_cmds.append("delete /Windows/System32/winpeshl.ini")
        update_cmds.append(f"add {iso_dir / 'setup.exe'} /setup.exe")
        update_cmds.append(f"add {iso_dir / 'sources' / 'inf' / 'setup.cfg'} /sources/inf/setup.cfg")
        update_cmds.append(f"add {iso_dir / 'sources' / bckimg} /sources/background.bmp")
        update_cmds.append(f"add {iso_dir / 'sources' / bckimg} /Windows/system32/setup.bmp")
        update_cmds.append(f"add {iso_dir / 'sources' / bckimg} /Windows/system32/winpe.jpg")
        update_cmds.append(f"add {iso_dir / 'sources' / bckimg} /Windows/system32/winre.jpg")

        update_script = "\n".join(update_cmds) + "\n"
        log.debug("wimlib-imagex update stdin:\n%s", update_script)
        subprocess.run(
            ["wimlib-imagex", "update", str(boot_wim), "2"],
            input=update_script,
            text=True,
            check=True,
        )

        _run("wimlib-imagex", "optimize", str(boot_wim))

        # Clean up temporary extraction
        xmllite = iso_dir / "sources" / "xmllite.dll"
        xmllite.unlink(missing_ok=True)
        winpe_jpg = iso_dir / "sources" / "winpe.jpg"
        winpe_jpg.unlink(missing_ok=True)

        # Mark index 2 flags and set it as bootable
        _run("wimlib-imagex", "info", str(boot_wim), "2",
             "--image-property", "FLAGS=2")
        _run("wimlib-imagex", "info", str(boot_wim), "2", "--boot")

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_background(iso_dir: Path) -> str:
        """Return the filename of the best available background image."""
        sources = iso_dir / "sources"
        candidates = [
            "background_svr.bmp",
            "background_cli.bmp",
            "background_svr.png",
            "background_cli.png",
            "winpe.jpg",
        ]
        for name in candidates:
            if (sources / name).exists():
                return name
        return "background_cli.bmp"   # fallback — may not exist, caller handles error

    @staticmethod
    def _make_display_name(edition_id: str, raw_name: str) -> str:
        """
        Build the WIM image display name used when exporting install images.
        Mirrors the shell script logic:
          - "Windows 10 <edition>" by default
          - "Windows 11 <edition>" when the build name mentions Windows 11
          - "Windows Server <year> <edition>" for server editions
        """
        if re.search(r"Windows 11", raw_name, re.IGNORECASE):
            return f"Windows 11 {edition_id}"
        if re.search(r"^Server", edition_id, re.IGNORECASE):
            year = "2022"
            for y in ("2025", "2028"):
                if y in raw_name:
                    year = y
            return f"Windows Server {year} {edition_id}"
        return f"Windows 10 {edition_id}"

    @staticmethod
    def _cleanup(iso_dir: Path, temp_dir: Path) -> None:
        shutil.rmtree(iso_dir,  ignore_errors=True)
        shutil.rmtree(temp_dir, ignore_errors=True)


def _warn(msg: str) -> None:
    if HAS_RICH:
        print_msg(f"[yellow]⚠[/yellow] {msg}")
    else:
        print(f"⚠ {msg}")