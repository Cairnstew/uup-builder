# uup-builder

[![PyPI version](https://badge.fury.io/py/uup-builder.svg)](https://pypi.org/project/uup-builder/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

A Python package and CLI tool for creating and customizing Windows ISO files using Microsoft's [Unified Update Platform (UUP)](https://learn.microsoft.com/en-us/windows/deployment/update/windows-update-overview).

## Overview

`uup-builder` provides a simple way to download Windows update packages from the UUP dump API, download the necessary files from Microsoft's servers, and convert them into bootable ISO images. It supports selecting specific editions, languages, and offers both a programmatic Python API and an interactive command-line interface.

This tool is ideal for developers, system administrators, or enthusiasts who need custom Windows installations for testing, deployment, or personal use.

## Features

- Search and list available Windows builds from the UUP dump database
- Interactive selection of builds, languages, and editions
- Download UUP files with resume support, parallel downloads, and SHA-1 verification
- Convert UUP files to bootable ISO images using the official `convert.sh` script
- Support for compression types (WIM or ESD)
- CI/CD friendly with GitHub Actions support
- Rich terminal output (via `rich` library, optional)

## Requirements

### Python
- Python 3.10 or higher

### System Dependencies
The conversion step requires the following binaries:
- `aria2c`
- `cabextract`
- `wimlib-imagex`
- `chntpw`
- `genisoimage` or `mkisofs`

Run `uup-builder convert` and it will prompt to install them if missing.

Alternatively, the Nix build will include the required dependencies in the CLI.

**Note:** Conversion is not supported on Windows; use Linux or macOS for ISO building.

## Installation

### From PyPI
```bash
pip install uup-builder
```

### From Source
```bash
git clone https://github.com/Cairnstew/uup-builder.git
cd uup-builder
pip install -e .
```

### Using uv (Recommended for Development)
```bash
uv sync
```

### Using Nix
If Nix is installed:
```bash
nix --extra-experimental-features 'nix-command flakes' run github:Cairnstew/uup-builder -- -h
```
([Google Colab Example](https://colab.research.google.com/drive/1LK-aG2bzhLDo4HyMl2kjQ9VULPGwjtiY?usp=sharing))

## Usage

`uup-builder` can be used via the command-line interface or as a Python library.

### Command-Line Interface

Run `uup-builder --help` for full options.

#### Key Commands

- **List Builds**
  ```bash
  uup-builder list --search "Windows 11"
  ```
  Lists available builds matching the search query.

- **List Languages**
  ```bash
  uup-builder langs --id <UUID>
  ```
  Lists languages for a specific build UUID.

- **List Editions**
  ```bash
  uup-builder editions --id <UUID> --lang en-us
  ```
  Lists editions for a build and language.

- **Download UUP Files**
  ```bash
  uup-builder download --id <UUID> --lang en-us --edition professional --out UUPs
  ```
  Downloads files to the specified directory (interactive if options omitted).

- **Convert to ISO**
  ```bash
  uup-builder convert --uup-dir UUPs --compress wim
  ```
  Converts downloaded UUP files to an ISO.

- **Full Build Pipeline**
  ```bash
  uup-builder build --search "Windows 11" --lang en-us --edition professional
  ```
  Interactively or directly downloads and builds the ISO.

Example full command:
```bash
uup-builder build --id <UUID> --lang en-us --edition professional --out UUPs --concurrency 8 --compress esd
```

Use `--verbose` for detailed logging.

### Python API

```python
from uup_builder import UUPClient, Downloader, Converter

# Initialize client
client = UUPClient()

# List builds
builds = client.list_builds(search="Windows 11", sort_by_date=True)

# Get files metadata for a specific build/language/edition
file_data = client.get_files(update_id="your-uuid", lang="en-us", edition="professional")

# Download files
dl = Downloader(out_dir="UUPs", concurrency=4)
dl.download_all(file_data)

# Convert to ISO
cv = Converter(compress="wim")
cv.convert(uup_dir="UUPs")
```

For interactive selection, use functions from `uup_builder.interactive`.

## Development

### Setup
```bash
git clone https://github.com/Cairnstew/uup-builder.git
cd uup-builder
uv sync
```

### Running Tests
```bash
pytest
```

### Project Structure
```
uup-builder/
├── src/                  # Package source code
│   └── uup_builder/
│       ├── __init__.py
│       ├── api.py        # UUP API client
│       ├── cli.py        # Command-line interface
│       ├── converter.py  # ISO conversion
│       ├── deps.py       # Dependency installer
│       ├── downloader.py # File downloader
│       ├── interactive.py# Pickers for CLI
│       └── output.py     # Console helpers
├── .github/workflows/    # CI/CD pipelines
├── pyproject.toml        # Project metadata and dependencies
├── pytest.ini            # Test configuration
├── flake.nix             # Nix development shell
└── uv.lock               # Locked dependencies
```

## License

This project is licensed under the [MIT License](LICENSE).

## Disclaimer

This project is not affiliated with or endorsed by Microsoft Corporation. Windows is a trademark of Microsoft Corporation. Use of UUP download functionality is subject to Microsoft's terms of service.