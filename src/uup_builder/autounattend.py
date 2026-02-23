"""
uup_builder.autounattend
~~~~~~~~~~~~~~~~~~~~~~~~

Support for injecting a Windows answer file (autounattend.xml / unattend.xml)
into the UUP directory before ISO conversion.

The user supplies a pre-built answer file — generated however they like
(e.g. via https://github.com/Cairnstew/GenerateAnswerFile, Windows SIM, or
hand-edited).  This module validates and copies it into the right place so
the converter picks it up automatically.

Quickstart::

    from uup_builder.autounattend import AnswerFile

    af = AnswerFile("~/my-autounattend.xml")
    af.inject(uup_dir="./UUPs")

    cv = Converter(converter_dir="./converter")
    cv.convert(uup_dir="./UUPs")
"""

from __future__ import annotations

import shutil
from pathlib import Path

# The filename the Windows installer looks for at the root of the ISO/media.
_ANSWER_FILE_NAME = "autounattend.xml"


class AnswerFile:
    """A user-supplied Windows answer file ready to be injected into a UUP build.

    Args:
        path: Path to the existing answer file on disk.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file does not have a .xml extension.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

        if not self.path.exists():
            raise FileNotFoundError(f"Answer file not found: {self.path}")

        if self.path.suffix.lower() != ".xml":
            raise ValueError(
                f"Answer file must be an XML file, got: {self.path.name}"
            )

    def inject(self, uup_dir: str | Path) -> Path:
        """Copy the answer file into *uup_dir* as ``autounattend.xml``.

        The converter will pick it up from there and embed it in the ISO.

        Args:
            uup_dir: The UUP working directory passed to :class:`~uup_builder.Converter`.

        Returns:
            The path of the copied file inside *uup_dir*.
        """
        dest = Path(uup_dir) / _ANSWER_FILE_NAME
        shutil.copy2(self.path, dest)
        return dest