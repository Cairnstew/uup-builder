"""
pytest configuration for uup_builder tests.
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub out uup_dump_api so ALL test modules can import uup_builder.*
# without the real library being installed.
# ---------------------------------------------------------------------------

def _make_stub():
    stub = MagicMock()
    for exc_name in (
        "UUPDumpAPIError",
        "UUPDumpConnectionError",
        "UUPDumpResponseError",
        "UUPDumpTimeoutError",
    ):
        exc_class = type(exc_name, (Exception,), {"error_code": "STUB_ERROR"})
        setattr(stub.exceptions, exc_name, exc_class)
    return stub


_stub = _make_stub()
sys.modules.setdefault("uup_dump_api", _stub)
sys.modules.setdefault("uup_dump_api.adapter", _stub.adapter)
sys.modules.setdefault("uup_dump_api.exceptions", _stub.exceptions)