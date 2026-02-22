"""
Tests for uup_builder.api (UUPClient)
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / stubs so the module can be imported without the real dependency
# ---------------------------------------------------------------------------

# Stub out uup_dump_api so we can import uup_builder.api without it installed
uup_dump_api_stub = MagicMock()
uup_dump_api_stub.adapter.RestAdapter = MagicMock
uup_dump_api_stub.exceptions.UUPDumpAPIError = type("UUPDumpAPIError", (Exception,), {})
uup_dump_api_stub.exceptions.UUPDumpConnectionError = type("UUPDumpConnectionError", (Exception,), {})
uup_dump_api_stub.exceptions.UUPDumpResponseError = type(
    "UUPDumpResponseError", (Exception,), {"error_code": "TEST_ERROR"}
)
uup_dump_api_stub.exceptions.UUPDumpTimeoutError = type("UUPDumpTimeoutError", (Exception,), {})

sys.modules.setdefault("uup_dump_api", uup_dump_api_stub)
sys.modules.setdefault("uup_dump_api.adapter", uup_dump_api_stub.adapter)
sys.modules.setdefault("uup_dump_api.exceptions", uup_dump_api_stub.exceptions)

from uup_builder.api import UUPClient, UUPClientError  # noqa: E402


# ---------------------------------------------------------------------------
# list_builds
# ---------------------------------------------------------------------------

class TestListBuilds:
    def _make_client(self) -> UUPClient:
        client = UUPClient.__new__(UUPClient)
        client._api = MagicMock()
        return client

    def test_returns_list_from_dict_response(self):
        client = self._make_client()
        client._api.listid.return_value = {
            "response": {
                "builds": {
                    "uuid-1": {"title": "Windows 11", "build": "22621", "arch": "amd64"},
                    "uuid-2": {"title": "Windows 10", "build": "19045", "arch": "amd64"},
                }
            }
        }
        result = client.list_builds(search="Windows")
        assert len(result) == 2
        uuids = {b["uuid"] for b in result}
        assert uuids == {"uuid-1", "uuid-2"}

    def test_returns_list_from_list_response(self):
        client = self._make_client()
        builds = [
            {"uuid": "a", "title": "Win11", "build": "22621", "arch": "amd64"},
        ]
        client._api.listid.return_value = {"response": {"builds": builds}}
        result = client.list_builds()
        assert result == builds

    def test_empty_builds_returns_empty_list(self):
        client = self._make_client()
        client._api.listid.return_value = {"response": {"builds": {}}}
        assert client.list_builds() == []

    def test_passes_search_and_sort_flag(self):
        client = self._make_client()
        client._api.listid.return_value = {"response": {"builds": {}}}
        client.list_builds(search="foo", sort_by_date=True)
        client._api.listid.assert_called_once_with(search="foo", sortByDate=True)

    def test_empty_search_passes_empty_string(self):
        client = self._make_client()
        client._api.listid.return_value = {"response": {"builds": {}}}
        client.list_builds(search=None)
        client._api.listid.assert_called_once_with(search="", sortByDate=False)

    def test_api_error_calls_bail(self):
        client = self._make_client()
        UUPDumpAPIError = uup_dump_api_stub.exceptions.UUPDumpAPIError
        client._api.listid.side_effect = UUPDumpAPIError("network failure")
        with pytest.raises(SystemExit):
            client.list_builds()

    def test_uuid_injected_into_dict_items(self):
        client = self._make_client()
        client._api.listid.return_value = {
            "response": {
                "builds": {
                    "my-uuid": {"title": "Test Build", "build": "12345", "arch": "x86"},
                }
            }
        }
        result = client.list_builds()
        assert result[0]["uuid"] == "my-uuid"


# ---------------------------------------------------------------------------
# list_langs
# ---------------------------------------------------------------------------

class TestListLangs:
    def _make_client(self) -> UUPClient:
        client = UUPClient.__new__(UUPClient)
        client._api = MagicMock()
        return client

    def test_returns_lang_list_and_names(self):
        client = self._make_client()
        client._api.list_langs.return_value = {
            "response": {
                "langList": ["en-us", "de-de"],
                "langFancyNames": {"en-us": "English (US)", "de-de": "German"},
            }
        }
        langs, names = client.list_langs("some-uuid")
        assert langs == ["en-us", "de-de"]
        assert names["de-de"] == "German"

    def test_passes_update_id(self):
        client = self._make_client()
        client._api.list_langs.return_value = {"response": {"langList": [], "langFancyNames": {}}}
        client.list_langs("target-uuid")
        client._api.list_langs.assert_called_once_with(updateId="target-uuid")

    def test_response_error_exits(self):
        client = self._make_client()
        UUPDumpResponseError = uup_dump_api_stub.exceptions.UUPDumpResponseError
        err = UUPDumpResponseError("bad")
        err.error_code = "FAILED"
        client._api.list_langs.side_effect = err
        with pytest.raises(SystemExit):
            client.list_langs("uuid")


# ---------------------------------------------------------------------------
# list_editions
# ---------------------------------------------------------------------------

class TestListEditions:
    def _make_client(self) -> UUPClient:
        client = UUPClient.__new__(UUPClient)
        client._api = MagicMock()
        return client

    def test_returns_edition_list_and_names(self):
        client = self._make_client()
        client._api.list_editions.return_value = {
            "response": {
                "editionList": ["professional", "core"],
                "editionFancyNames": {"professional": "Windows 11 Pro", "core": "Windows 11 Home"},
            }
        }
        editions, names = client.list_editions("uuid", "en-us")
        assert editions == ["professional", "core"]
        assert names["professional"] == "Windows 11 Pro"

    def test_passes_correct_params(self):
        client = self._make_client()
        client._api.list_editions.return_value = {
            "response": {"editionList": [], "editionFancyNames": {}}
        }
        client.list_editions("my-uuid", "fr-fr")
        client._api.list_editions.assert_called_once_with(lang="fr-fr", updateId="my-uuid")


# ---------------------------------------------------------------------------
# get_files
# ---------------------------------------------------------------------------

class TestGetFiles:
    def _make_client(self) -> UUPClient:
        client = UUPClient.__new__(UUPClient)
        client._api = MagicMock()
        client._api.timeout = 30
        return client

    def _mock_response(self, body: dict):
        mock_resp = MagicMock()
        mock_resp.json.return_value = body
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 200
        return mock_resp

    def test_returns_parsed_file_data(self):
        client = self._make_client()
        payload = {
            "response": {
                "updateName": "Windows 11 22H2",
                "arch": "amd64",
                "build": "22621.1",
                "files": {
                    "Windows11.esd": {"sha1": "abc123", "size": "1000", "url": "http://cdn/file.esd"}
                },
            }
        }
        with patch("requests.get", return_value=self._mock_response(payload)):
            data = client.get_files("uuid", "en-us", "professional")

        assert data["updateName"] == "Windows 11 22H2"
        assert data["arch"] == "amd64"
        assert "Windows11.esd" in data["files"]

    def test_api_error_in_response_exits(self):
        client = self._make_client()
        payload = {"response": {"error": "WRONG_EDITION"}}
        with patch("requests.get", return_value=self._mock_response(payload)):
            with pytest.raises(SystemExit):
                client.get_files("uuid", "en-us", "bad-edition")

    def test_request_exception_exits(self):
        import requests as req
        client = self._make_client()
        with patch("requests.get", side_effect=req.RequestException("timeout")):
            with pytest.raises(SystemExit):
                client.get_files("uuid", "en-us", "professional")

    def test_params_sent_correctly(self):
        client = self._make_client()
        payload = {"response": {"updateName": "", "arch": "", "build": "", "files": {}}}
        with patch("requests.get", return_value=self._mock_response(payload)) as mock_get:
            client.get_files("MY-UUID", "EN-US", "PROFESSIONAL")
            call_kwargs = mock_get.call_args
            params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1]
            assert params["id"] == "MY-UUID"
            assert params["lang"] == "en-us"        # lowercased
            assert params["edition"] == "professional"  # lowercased