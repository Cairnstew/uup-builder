"""
uup_builder.api
---------------
Thin, typed wrapper around ``uup_dump_api.RestAdapter``
(Cairnstew/uup-dump-api-py).

All public methods raise :class:`UUPClientError` on failure so callers
don't need to import uup_dump_api exceptions directly.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from uup_builder.output import bail

try:
    from uup_dump_api.adapter import RestAdapter
    from uup_dump_api.exceptions import (
        UUPDumpAPIError,
        UUPDumpConnectionError,
        UUPDumpResponseError,
        UUPDumpTimeoutError,
    )
except ImportError:
    sys.exit(
        "uup-dump-api-py is not installed.\n"
        "Run: pip install git+https://github.com/Cairnstew/uup-dump-api-py.git"
    )

__all__ = ["UUPClient", "UUPClientError"]

log = logging.getLogger(__name__)


class UUPClientError(RuntimeError):
    """Raised when the UUP dump API returns an error."""


class UUPClient:
    """
    High-level client for the UUP dump JSON API.

    Parameters
    ----------
    timeout:
        HTTP request timeout in seconds (default 30).
    verbose:
        Pass ``True`` to enable DEBUG-level logging inside the adapter.
    """

    def __init__(self, timeout: int = 30, verbose: bool = False) -> None:
        level = logging.DEBUG if verbose else logging.INFO
        self._api = RestAdapter(timeout=timeout, log_level=level)

    # ------------------------------------------------------------------
    # Builds
    # ------------------------------------------------------------------

    def list_builds(
        self,
        search: Optional[str] = None,
        sort_by_date: bool = False,
    ) -> list[dict]:
        """
        Return a list of build dicts from the UUP dump database.

        Each dict contains at least: ``uuid``, ``title``, ``build``, ``arch``.

        Parameters
        ----------
        search:
            Optional search string (e.g. ``"Windows 11"``).
        sort_by_date:
            Sort results by the date they were added to the database.
        """
        try:
            result = self._api.listid(search=search or "", sortByDate=sort_by_date)
        except (UUPDumpAPIError, UUPDumpConnectionError, UUPDumpTimeoutError) as exc:
            bail(f"Failed to list builds: {exc}")

        resp = result.get("response", {})
        raw = resp.get("builds", {})

        # The API may return a dict keyed by UUID, or a plain list
        if isinstance(raw, dict):
            builds: list[dict] = []
            for uuid, info in raw.items():
                info.setdefault("uuid", uuid)
                builds.append(info)
        else:
            builds = list(raw)

        log.debug("list_builds returned %d result(s)", len(builds))
        return builds

    # ------------------------------------------------------------------
    # Languages
    # ------------------------------------------------------------------

    def list_langs(
        self,
        update_id: str,
    ) -> tuple[list[str], dict[str, str]]:
        """
        Return ``(lang_list, lang_fancy_names)`` for the given update UUID.

        ``lang_list`` is ordered; ``lang_fancy_names`` maps code → display name.
        """
        try:
            result = self._api.list_langs(updateId=update_id)
        except UUPDumpResponseError as exc:
            bail(f"API error listing languages [{exc.error_code}]: {exc}")
        except UUPDumpAPIError as exc:
            bail(f"Failed to list languages: {exc}")

        resp = result.get("response", {})
        return resp.get("langList", []), resp.get("langFancyNames", {})

    # ------------------------------------------------------------------
    # Editions
    # ------------------------------------------------------------------

    def list_editions(
        self,
        update_id: str,
        lang: str,
    ) -> tuple[list[str], dict[str, str]]:
        """
        Return ``(edition_list, edition_fancy_names)`` for the given update + language.
        """
        try:
            result = self._api.list_editions(lang=lang, updateId=update_id)
        except UUPDumpResponseError as exc:
            bail(f"API error listing editions [{exc.error_code}]: {exc}")
        except UUPDumpAPIError as exc:
            bail(f"Failed to list editions: {exc}")

        resp = result.get("response", {})
        return resp.get("editionList", []), resp.get("editionFancyNames", {})

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def get_files(
        self,
        update_id: str,
        lang: str,
        edition: str,
    ) -> dict:
        """
        Return file metadata for the given update / language / edition.

        Returns a dict with keys:

        ``updateName``, ``arch``, ``build``, ``files``

        ``files`` is a dict mapping filename -> ``{sha1, size, url, ...}``.

        Note: calls the API directly because the library sends ``pack=``
        instead of ``lang=``, causing a 400 Bad Request.
        """
        import requests as _requests

        url = "https://api.uupdump.net/get.php"
        params = {
            "id":      update_id,
            "lang":    lang.lower(),
            "edition": edition.lower(),
        }
        log.debug("GET %s params=%s", url, params)

        timeout = getattr(self._api, "timeout", 30)
        try:
            r = _requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
        except _requests.RequestException as exc:
            bail(f"Failed to fetch file list: {exc}")

        body = r.json()
        if "error" in body.get("response", {}):
            bail(f"API error fetching files: {body['response']['error']}")

        resp = body.get("response", {})
        data = {
            "updateName": resp.get("updateName", ""),
            "arch":       resp.get("arch", ""),
            "build":      resp.get("build", ""),
            "files":      resp.get("files", {}),
        }
        log.debug("get_files: %d file(s) for %s/%s/%s", len(data["files"]), update_id, lang, edition)
        return data