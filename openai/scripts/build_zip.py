#!/usr/bin/env python3
"""Validate, then zip the OpenAI plugin package into dist/drinkedin-night-out-openai.zip.

The ZIP holds only the package: plugin.json and mcp.json at its root, skills/ and assets/. No
scripts, README or dist/. Entries are sorted with a fixed timestamp, so the same sources give the
same bytes. Usage: python3 scripts/build_zip.py [--release]
"""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate  # noqa: E402

ROOT = validate.ROOT
OUT = ROOT / "dist" / "drinkedin-night-out-openai.zip"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def package_files():
    files = []
    for entry in validate.PACKAGE_ENTRIES:
        path = ROOT / entry
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in path.rglob("*") if p.is_file() and p.name != ".DS_Store")
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def main(argv):
    if validate.main(argv) != 0:
        print("validation failed: no ZIP built")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in package_files():
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    with zipfile.ZipFile(OUT) as zf:
        names = zf.namelist()
    print(f"\nwrote {OUT} ({OUT.stat().st_size} bytes):")
    for n in names:
        print(f"  {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
