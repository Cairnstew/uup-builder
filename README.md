# uup-builder-py

A Python package for creating and customizing Windows ISO files using the [Unified Update Platform (UUP)](https://learn.microsoft.com/en-us/windows/deployment/update/windows-update-overview).

## Overview

`uup-builder-py` provides a programmatic interface to download Windows update packages from Microsoft's Unified Update Platform and convert them into bootable ISO files. It allows you to select specific Windows editions, languages, and components, giving you full control over the resulting image.

## Features

- Download Windows packages directly from Microsoft's UUP servers
- Build customized Windows ISO files
- Select target Windows edition and language
- Scriptable and automatable via Python API
- CI/CD ready with GitHub Actions support

## Requirements

- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) (recommended for dependency management)

## Installation

### With pip

```bash
pip install uup-builder-py
```

### From source

```bash
git clone https://github.com/Cairnstew/uup-builder-py.git
cd uup-builder-py
pip install -e .
```

### With uv

```bash
uv sync
```

### With Nix

A `flake.nix` is provided for reproducible development environments:

```bash
nix develop
```

## Usage

> ⚠️ **Note:** Fill in usage examples based on the package's public API.

```python
from uup_builder import ...  # update with actual import

# Example: build a Windows 11 ISO
builder = ...
builder.build(edition="pro", lang="en-us", output="windows11.iso")
```

## Development

### Setup

```bash
git clone https://github.com/Cairnstew/uup-builder-py.git
cd uup-builder-py
uv sync
```

### Running tests

```bash
pytest
```

## Project Structure

```
uup-builder-py/
├── src/                  # Package source code
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