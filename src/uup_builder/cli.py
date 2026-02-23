"""
uup_builder.cli
---------------
Argument parser and command handlers for the ``uup_builder`` CLI.

Entry points
------------
* ``python -m uup_builder``
* The ``uup-builder`` console script (if installed via pyproject.toml)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from uup_builder.api import UUPClient
from uup_builder.autounattend import AnswerFile
from uup_builder.converter import Converter
from uup_builder.downloader import Downloader, DEFAULT_CONCURRENCY, DEFAULT_OUT
from uup_builder.interactive import pick_build, pick_edition, pick_lang
from uup_builder.output import (
    HAS_RICH,
    bail,
    console,
    print_info,
    print_ok,
    setup_logging,
)

if HAS_RICH:
    from rich.table import Table

__all__ = ["build_parser", "main"]


# ---------------------------------------------------------------------------
# Shared argument helpers
# ---------------------------------------------------------------------------

def _add_verbose(p: argparse.ArgumentParser) -> None:
    p.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG logging")


def _add_answer_file(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--answer-file",
        metavar="FILE",
        default=None,
        help="Path to an autounattend.xml answer file to embed in the ISO",
    )


def _resolve_build_lang_edition(
    client: UUPClient,
    args: argparse.Namespace,
) -> tuple[str, str, str]:
    """
    Return ``(update_id, lang, edition)``, prompting interactively for any
    that were not supplied on the command line.
    """
    update_id: str = args.id
    lang: str = args.lang
    edition: str = args.edition

    if not update_id:
        build = pick_build(client, search=getattr(args, "search", None))
        update_id = build["uuid"]
        print_ok(f"Build: {build.get('title', update_id)}")

    if not lang:
        lang = pick_lang(client, update_id)
        print_ok(f"Language: {lang}")

    if not edition:
        edition = pick_edition(client, update_id, lang)
        print_ok(f"Edition: {edition}")

    return update_id, lang, edition


def _maybe_inject_answer_file(args: argparse.Namespace, uup_dir: str | Path) -> None:
    """Inject an answer file into *uup_dir* if ``--answer-file`` was supplied."""
    if getattr(args, "answer_file", None):
        af = AnswerFile(args.answer_file)
        dest = af.inject(uup_dir)
        print_ok(f"Answer file injected: {dest}")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    client = UUPClient(verbose=args.verbose)
    builds = client.list_builds(
        search=args.search,
        sort_by_date=args.sort_by_date,
    )
    if not builds:
        print("No builds found.")
        return

    if HAS_RICH:
        t = Table(title="UUP Dump Builds", show_lines=True)
        t.add_column("Title")
        t.add_column("Build", style="yellow")
        t.add_column("Arch", style="green")
        t.add_column("UUID", style="dim")
        for b in builds:
            t.add_row(
                b.get("title", ""),
                b.get("build", ""),
                b.get("arch", ""),
                b.get("uuid", ""),
            )
        console.print(t)
    else:
        for b in builds:
            print(
                f"[{b.get('arch', '?')}] {b.get('title', '')}  "
                f"build={b.get('build', '')}  uuid={b.get('uuid', '')}"
            )


def cmd_langs(args: argparse.Namespace) -> None:
    client = UUPClient(verbose=args.verbose)
    lang_list, lang_names = client.list_langs(args.id)

    if HAS_RICH:
        t = Table(title=f"Languages — {args.id}")
        t.add_column("Code", style="yellow")
        t.add_column("Name")
        for code in lang_list:
            t.add_row(code, lang_names.get(code, ""))
        console.print(t)
    else:
        for code in lang_list:
            print(f"  {code}  {lang_names.get(code, '')}")


def cmd_editions(args: argparse.Namespace) -> None:
    client = UUPClient(verbose=args.verbose)
    edition_list, edition_names = client.list_editions(args.id, args.lang)

    if HAS_RICH:
        t = Table(title=f"Editions — {args.id} / {args.lang}")
        t.add_column("Code", style="yellow")
        t.add_column("Name")
        for code in edition_list:
            t.add_row(code, edition_names.get(code, ""))
        console.print(t)
    else:
        for code in edition_list:
            print(f"  {code}  {edition_names.get(code, '')}")


def cmd_download(args: argparse.Namespace) -> None:
    client = UUPClient(verbose=args.verbose)
    update_id, lang, edition = _resolve_build_lang_edition(client, args)

    file_data = client.get_files(update_id, lang, edition)

    dl = Downloader(
        out_dir=args.out,
        concurrency=args.concurrency,
        no_resume=args.no_resume,
    )
    dl.download_all(file_data)


def cmd_convert(args: argparse.Namespace) -> None:
    uup_dir = Path(args.uup_dir)
    if not uup_dir.is_dir():
        bail(f"UUP directory not found: {uup_dir}")

    _maybe_inject_answer_file(args, uup_dir)

    cv = Converter(compress=args.compress)
    cv.convert(uup_dir=uup_dir, iso_out=args.iso_out)


def cmd_build(args: argparse.Namespace) -> None:
    """Full pipeline: resolve build/lang/edition → download → convert."""
    client = UUPClient(verbose=args.verbose)
    update_id, lang, edition = _resolve_build_lang_edition(client, args)

    file_data = client.get_files(update_id, lang, edition)

    dl = Downloader(
        out_dir=args.out,
        concurrency=args.concurrency,
        no_resume=args.no_resume,
    )
    dl.download_all(file_data)

    if args.no_convert:
        print_info("Skipping ISO conversion (--no-convert).")
        return

    _maybe_inject_answer_file(args, args.out)

    cv = Converter(compress=args.compress)
    cv.convert(uup_dir=args.out, iso_out=args.iso_out)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uup-builder",
        description="Build a Windows ISO from UUP dump using Cairnstew/uup-dump-api-py.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- list ----------------------------------------------------------------
    p = sub.add_parser("list", help="List / search available builds")
    p.add_argument("--search", metavar="QUERY", help="Search query (e.g. 'Windows 11')")
    p.add_argument("--sort-by-date", action="store_true")
    _add_verbose(p)
    p.set_defaults(func=cmd_list)

    # -- langs ---------------------------------------------------------------
    p = sub.add_parser("langs", help="List languages for a build UUID")
    p.add_argument("--id", required=True, metavar="UUID")
    _add_verbose(p)
    p.set_defaults(func=cmd_langs)

    # -- editions ------------------------------------------------------------
    p = sub.add_parser("editions", help="List editions for a build + language")
    p.add_argument("--id", required=True, metavar="UUID")
    p.add_argument("--lang", required=True, metavar="CODE")
    _add_verbose(p)
    p.set_defaults(func=cmd_editions)

    # -- download ------------------------------------------------------------
    p = sub.add_parser("download", help="Download UUP files (no ISO conversion)")
    p.add_argument("--id", metavar="UUID", default=None)
    p.add_argument("--search", metavar="QUERY", default=None)
    p.add_argument("--lang", metavar="CODE", default=None)
    p.add_argument("--edition", metavar="NAME", default=None)
    p.add_argument("--out", metavar="DIR", default=DEFAULT_OUT,
                   help=f"Download directory (default: {DEFAULT_OUT})")
    p.add_argument("--concurrency", metavar="N", type=int, default=DEFAULT_CONCURRENCY,
                   help=f"Parallel downloads (default: {DEFAULT_CONCURRENCY})")
    p.add_argument("--no-resume", action="store_true",
                   help="Delete partial files and re-download from scratch")
    _add_verbose(p)
    p.set_defaults(func=cmd_download)

    # -- convert -------------------------------------------------------------
    p = sub.add_parser("convert", help="Convert downloaded UUP files to ISO")
    p.add_argument("--uup-dir", metavar="DIR", default=DEFAULT_OUT,
                   help=f"Directory with UUP files (default: {DEFAULT_OUT})")
    p.add_argument("--compress", default="wim", choices=["wim", "esd"],
                   help="Compression type: wim (default) or esd")
    p.add_argument("--iso-out", metavar="FILE", default=None,
                   help="Explicit output ISO path (optional)")
    _add_answer_file(p)
    _add_verbose(p)
    p.set_defaults(func=cmd_convert)

    # -- build (full pipeline) -----------------------------------------------
    p = sub.add_parser("build", help="Full pipeline: pick → download → build ISO")
    p.add_argument("--id", metavar="UUID", default=None)
    p.add_argument("--search", metavar="QUERY", default=None)
    p.add_argument("--lang", metavar="CODE", default=None)
    p.add_argument("--edition", metavar="NAME", default=None)
    p.add_argument("--out", metavar="DIR", default=DEFAULT_OUT,
                   help=f"UUP download directory (default: {DEFAULT_OUT})")
    p.add_argument("--concurrency", metavar="N", type=int, default=DEFAULT_CONCURRENCY,
                   help=f"Parallel downloads (default: {DEFAULT_CONCURRENCY})")
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--compress", default="wim", choices=["wim", "esd"],
                   help="Compression type: wim (default) or esd")
    p.add_argument("--iso-out", metavar="FILE", default=None)
    p.add_argument("--no-convert", action="store_true",
                   help="Skip ISO conversion (download UUP files only)")
    _add_answer_file(p)
    _add_verbose(p)
    p.set_defaults(func=cmd_build)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(getattr(args, "verbose", False))
    args.func(args)


if __name__ == "__main__":
    main()