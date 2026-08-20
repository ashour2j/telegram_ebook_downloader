#!/usr/bin/env python3
"""
One-command library update: rename + flatten new downloads, then rebuild the
Excel database, JSON feed and CSV.

Usage:
    python update_library.py

This is the same as running:
    python rename_library.py --apply
    python build_database.py
"""

import sys
from pathlib import Path

from build_database import build
from config import DownloaderConfig
from rename_library import rename_library


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    cfg = DownloaderConfig()
    base_dir = Path(cfg.output_dir)
    if not base_dir.is_dir():
        print(f"[!] Library directory not found: {base_dir}", file=sys.stderr)
        sys.exit(1)

    flat_dir = base_dir / "library"
    print("== Step 1/2: rename + flatten library ==")
    records = rename_library(
        base_dir,
        flat_dir,
        base_dir / "books_catalog.csv",
        base_dir / "books_catalog.json",
        apply=True,
        dedup_size=True,
    )
    if records is None:
        print("[!] No ebook files found; aborting.", file=sys.stderr)
        sys.exit(1)

    print("\n== Step 2/2: rebuild database + website feed ==")
    books = build(
        base_dir,
        Path("books_database.xlsx"),
        Path("books_data.json"),
        Path("books.csv"),
        delete_duplicates=True,
    )
    if not books:
        sys.exit(1)

    print("\nLibrary updated. Reload the invoice app (or press 'تحديث المكتبة') to see the changes.")


if __name__ == "__main__":
    main()
