"""
uup_builder.interactive
-----------------------
Interactive terminal pickers for build, language, and edition selection.
Works with or without ``rich``.
"""

from __future__ import annotations

from typing import Callable

from uup_builder.api import UUPClient
from uup_builder.output import HAS_RICH, bail, console

if HAS_RICH:
    from rich.prompt import IntPrompt
    from rich.table import Table

__all__ = [
    "pick_build",
    "pick_lang",
    "pick_edition",
]


def _pick(items: list, label_fn: Callable, title: str) -> int:
    """
    Display *items* as a numbered list and return the chosen 0-based index.
    """
    if not items:
        bail(f"No {title} available.")

    if HAS_RICH:
        table = Table(title=title, show_lines=True)
        table.add_column("#", style="bold cyan", width=4)
        table.add_column("Value")
        for i, item in enumerate(items, 1):
            table.add_row(str(i), label_fn(item))
        console.print(table)
        choice = IntPrompt.ask(f"Select {title} #", default=1)
    else:
        for i, item in enumerate(items, 1):
            print(f"  {i:>3}. {label_fn(item)}")
        raw = input(f"Select {title} # [1]: ").strip()
        choice = int(raw) if raw else 1

    return max(1, min(choice, len(items))) - 1


def pick_build(client: UUPClient, search: str | None = None) -> dict:
    """
    Interactively choose a build from the UUP dump database.

    Parameters
    ----------
    client:
        A :class:`~uup_builder.api.UUPClient` instance.
    search:
        Optional search string to pre-filter the list.

    Returns
    -------
    dict
        The chosen build dict (contains ``uuid``, ``title``, ``build``, ``arch``).
    """
    builds = client.list_builds(search=search, sort_by_date=True)[:50]
    if not builds:
        bail("No builds found" + (f" matching '{search}'" if search else "") + ".")

    idx = _pick(
        builds,
        lambda b: f"[{b.get('arch', '?')}] {b.get('title', 'Unknown')}  "
                  f"(build {b.get('build', '?')})",
        title="Available Builds",
    )
    return builds[idx]


def pick_lang(client: UUPClient, update_id: str) -> str:
    """
    Interactively choose a language for *update_id*.

    Returns
    -------
    str
        The chosen language code (e.g. ``"en-us"``).
    """
    lang_list, lang_names = client.list_langs(update_id)
    idx = _pick(
        lang_list,
        lambda code: f"{code}  —  {lang_names.get(code, '')}",
        title="Available Languages",
    )
    return lang_list[idx]


def pick_edition(client: UUPClient, update_id: str, lang: str) -> str:
    """
    Interactively choose an edition for *update_id* + *lang*.

    Returns
    -------
    str
        The chosen edition name (e.g. ``"professional"``).
    """
    edition_list, edition_names = client.list_editions(update_id, lang)
    idx = _pick(
        edition_list,
        lambda code: f"{code}  —  {edition_names.get(code, '')}",
        title="Available Editions",
    )
    return edition_list[idx]