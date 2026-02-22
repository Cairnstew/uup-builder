"""
uup_builder — download UUP files from UUP dump and build Windows ISOs.

Uses Cairnstew/uup-dump-api-py as the API client.

Quickstart
----------
Programmatic use::

    from uup_builder import UUPClient, Downloader, Converter

    client    = UUPClient()
    builds    = client.list_builds(search="Windows 11")
    langs, _  = client.list_langs(builds[0]["uuid"])
    edns, _   = client.list_editions(builds[0]["uuid"], langs[0])
    files     = client.get_files(builds[0]["uuid"], langs[0], edns[0])

    dl  = Downloader(out_dir="./UUPs")
    dl.download_all(files)

    cv  = Converter(converter_dir="./converter")
    cv.convert(uup_dir="./UUPs")

CLI use::

    python -m uup_builder build
    python -m uup_builder build --id <UUID> --lang en-us --edition professional
    python -m uup_builder list --search "Windows 11"
"""

from uup_builder.api import UUPClient
from uup_builder.downloader import Downloader
from uup_builder.converter import Converter

__all__ = [
    "__version__",
    "UUPClient",
    "Downloader",
    "Converter",
]