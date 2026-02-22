"""
uup_builder.downloader
----------------------
Downloads UUP file sets from Microsoft CDN with resume support,
SHA-1 verification, and optional parallel downloads.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from uup_builder.output import HAS_RICH, bail, console, print_info, print_ok, print_err

try:
    import requests
except ImportError:
    sys.exit("requests is required: pip install requests")

if HAS_RICH:
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )

__all__ = ["Downloader"]

log = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 4
DEFAULT_OUT = "./UUPs"


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_one(
    url: str,
    dest: Path,
    expected_sha1: Optional[str],
    progress=None,
    overall_task=None,
) -> tuple[str, bool]:
    """Download *url* to *dest* with resume support. Returns ``(filename, ok)``."""
    existing = dest.stat().st_size if dest.exists() else 0
    headers = {"Range": f"bytes={existing}-"} if existing else {}

    try:
        r = requests.get(url, headers=headers, stream=True, timeout=60)
        if r.status_code == 416:
            pass  # server says we already have the whole file
        elif r.status_code in (200, 206):
            mode = "ab" if existing and r.status_code == 206 else "wb"
            with open(dest, mode) as f:
                for chunk in r.iter_content(chunk_size=1 << 17):
                    f.write(chunk)
                    if progress is not None and overall_task is not None:
                        progress.update(overall_task, advance=len(chunk))
        else:
            log.error("HTTP %s downloading %s", r.status_code, dest.name)
            return dest.name, False
    except requests.RequestException as exc:
        log.error("Download error for %s: %s", dest.name, exc)
        return dest.name, False

    if expected_sha1:
        actual = _sha1(dest)
        if actual.lower() != expected_sha1.lower():
            log.error(
                "SHA-1 mismatch for %s (expected %s, got %s)",
                dest.name, expected_sha1, actual,
            )
            dest.unlink(missing_ok=True)
            return dest.name, False

    return dest.name, True


class Downloader:
    """
    Downloads a UUP file set into a local directory.

    Parameters
    ----------
    out_dir:
        Directory to store downloaded files (created if absent).
    concurrency:
        Number of parallel download threads.
    no_resume:
        If ``True``, delete partial files and re-download from scratch.
    """

    def __init__(
        self,
        out_dir: str | Path = DEFAULT_OUT,
        concurrency: int = DEFAULT_CONCURRENCY,
        no_resume: bool = False,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.concurrency = concurrency
        self.no_resume = no_resume

    def download_all(self, file_data: dict) -> list[str]:
        """
        Download all files described by *file_data* (as returned by
        :meth:`UUPClient.get_files`).

        Returns a list of filenames that **failed** to download (empty = all OK).

        Parameters
        ----------
        file_data:
            Dict with keys ``updateName``, ``arch``, ``build``, ``files``.
        """
        files: dict = file_data.get("files", {})
        if not files:
            bail("No files in file_data — nothing to download.")

        self.out_dir.mkdir(parents=True, exist_ok=True)

        print_ok(
            f"Build: {file_data.get('updateName', '?')}  "
            f"[{file_data.get('arch', '?')}  build {file_data.get('build', '?')}]"
        )
        print_info(f"{len(files)} file(s) → {self.out_dir}")

        tasks: list[tuple[str, str, Path, Optional[str]]] = []
        for fname, info in files.items():
            dest = self.out_dir / fname
            if self.no_resume and dest.exists():
                dest.unlink()
            tasks.append((fname, info.get("url", ""), dest, info.get("sha1")))

        try:
            total_bytes = sum(int(info.get("size", 0)) for info in files.values())
        except (ValueError, TypeError):
            total_bytes = 0

        if total_bytes:
            print_info(f"Total size: {_human_size(total_bytes)}")

        failed: list[str] = []

        if HAS_RICH:
            failed = self._download_rich(tasks, total_bytes)
        else:
            failed = self._download_plain(tasks)

        if failed:
            print_err(f"{len(failed)} file(s) failed: {', '.join(failed)}")
        else:
            print_ok(f"All {len(files)} files downloaded to {self.out_dir}")

        return failed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _download_rich(self, tasks, total_bytes: int) -> list[str]:
        failed: list[str] = []
        prog = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        )
        with prog:
            overall = prog.add_task("[cyan]Downloading…", total=total_bytes or None)

            def _dl(args):
                _fname, url, dest, sha1 = args
                return _download_one(url, dest, sha1, prog, overall)

            with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
                futs = {ex.submit(_dl, t): t[0] for t in tasks}
                for fut in as_completed(futs):
                    name, ok = fut.result()
                    if not ok:
                        failed.append(name)
        return failed

    def _download_plain(self, tasks) -> list[str]:
        failed: list[str] = []
        for i, (fname, url, dest, sha1) in enumerate(tasks, 1):
            print(f"  [{i}/{len(tasks)}] {fname}")
            _, ok = _download_one(url, dest, sha1)
            if not ok:
                failed.append(fname)
        return failed