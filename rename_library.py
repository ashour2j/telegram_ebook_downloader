#!/usr/bin/env python3
"""
Scan the downloaded ebook library, parse every filename into structured
metadata (series, subject, grade, term, year, type...), rename all books to a
consistent Arabic-word schema, flatten them into a single folder, and export a
catalog (CSV + JSON) ready to import into a database.

Dry-run by default (prints the plan + writes the catalog only).
Use --apply to actually move/rename the files.

Example target name:
    سلاح التلميذ - عربي - الصف السادس الابتدائي - الترم الأول - 2027.pdf
"""

import argparse
import csv
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import DownloaderConfig
from grade_parser import detect_grade, normalize_arabic_text
from namer import sanitize_filename
from term_parser import detect_term

ALLOWED_EXTS = {".pdf", ".epub", ".mobi", ".azw3", ".djvu"}

# Egyptian stage names per grade (1..12)
GRADE_ARABIC = {
    1: "الصف الأول الابتدائي",
    2: "الصف الثاني الابتدائي",
    3: "الصف الثالث الابتدائي",
    4: "الصف الرابع الابتدائي",
    5: "الصف الخامس الابتدائي",
    6: "الصف السادس الابتدائي",
    7: "الصف الأول الإعدادي",
    8: "الصف الثاني الإعدادي",
    9: "الصف الثالث الإعدادي",
    10: "الصف الأول الثانوي",
    11: "الصف الثاني الثانوي",
    12: "الصف الثالث الثانوي",
}

TERM_ARABIC = {1: "الترم الأول", 2: "الترم الثاني"}

# Book series / publishers (patterns written against normalized Arabic text:
# أ->ا, ى->ي, ة->ه, combining hamza removed)
SERIES_PATTERNS = [
    (re.compile(r"سلاح\s*التلميذ"), "سلاح التلميذ"),
    (re.compile(r"سلاح\b"), "سلاح التلميذ"),
    (re.compile(r"الاضواء|اضواء"), "الاضواء"),
    (re.compile(r"المعاصر|معاصر"), "المعاصر"),
    (re.compile(r"التاسيس|التأسيس"), "التأسيس"),
    (re.compile(r"الشاطر"), "الشاطر"),
    (re.compile(r"النخبه|النخبة"), "النخبة"),
    (re.compile(r"قطر\s*الندي|قطر\s*الندى"), "قطر الندى"),
    (re.compile(r"الامتحان"), "الامتحان"),
    (re.compile(r"بوني"), "بوني"),
    (re.compile(r"جيم"), "جيم"),
]

# School subjects (normalized Arabic + a few English aliases)
SUBJECT_PATTERNS = [
    (re.compile(r"تكنولوجيا\s*المعلومات|معلومات|ict", re.I), "تكنولوجيا المعلومات"),
    (re.compile(r"فرنساوي|فرنسي|french", re.I), "فرنساوي"),
    (re.compile(r"انجليزي|انجلش|english", re.I), "انجليزي"),
    (re.compile(r"رياضيات|حساب|ماث|math", re.I), "رياضيات"),
    (re.compile(r"علوم|ساينس|science", re.I), "علوم"),
    (re.compile(r"دراسات|اجتماعيات|تاريخ|جغرافيا|history", re.I), "دراسات"),
    (re.compile(r"عربي|العربية|arabic", re.I), "عربي"),
]

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
GRADE_TOKEN_RE = re.compile(r"\d{1,2}\s*[ببععثث]")
GRADE_PHRASE_RE = re.compile("|".join(re.escape(g) for g in GRADE_ARABIC.values()))
GRADE_NUM_RE = re.compile(r"الصف\s*\d{1,2}\b")
PART_RE = re.compile(r"\(\d{1,2}\)")
SUPPLEMENT_RE = re.compile(r"ملحق")
REVIEW_RE = re.compile(r"مراجعه|مراجعة")
ANSWERS_RE = re.compile(r"(?:ال)?حلول|(?:ال)?اجابات|اجابه")
PUBLISHER_RE = re.compile(r"المتميزون|المتميزين")
TERM_PHRASE_RE = re.compile(
    r"(?:الترم|ترم)\s*(?:الاول|الثاني|التاني|اول|ثاني|تاني|1|2)\b|"
    r"الفصل\s*الدراسي\s*(?:الاول|الثاني|اول|ثاني|تاني)\b"
)


def _remove_first(text: str, pattern: re.Pattern) -> str:
    """Removes the first occurrence of the pattern from text."""
    match = pattern.search(text)
    if not match:
        return text
    return (text[: match.start()] + " " + text[match.end():]).strip()


def _folder_grade(folder: Path) -> Optional[int]:
    """Extracts grade number from a folder path like .../Grade_06_Primary_6/..."""
    match = re.search(r"Grade_?0?(\d+)", str(folder))
    return int(match.group(1)) if match else None


def parse_book(raw_name: str, folder: Path) -> Dict:
    """Parses a filename into structured metadata."""
    text = normalize_arabic_text(raw_name)
    text = re.sub(r"[\u064B-\u0655\u0670]", "", text)  # strip combining diacritics + hamza marks
    text = re.sub(r"\s+", " ", text).strip()

    meta = {
        "type": "كتاب",
        "series": "",
        "subject": "",
        "grade": None,
        "term": None,
        "year": None,
        "part": None,
        "publisher": "",
        "extra": "",
    }

    # Type: ملحق (supplement) / مراجعة (review) / حلول (answers) / كتاب (main book)
    if SUPPLEMENT_RE.search(text):
        meta["type"] = "ملحق"
        text = _remove_first(text, SUPPLEMENT_RE)
    elif REVIEW_RE.search(text):
        meta["type"] = "مراجعة"
        text = _remove_first(text, REVIEW_RE)
    elif ANSWERS_RE.search(text):
        meta["type"] = "حلول"
        text = _remove_first(text, ANSWERS_RE)

    # Year
    year_match = YEAR_RE.search(text)
    if year_match:
        meta["year"] = int(year_match.group(0))
        text = re.sub(YEAR_RE, " ", text)

    # Term (first / second)
    term_num, _ = detect_term(raw_name)
    if term_num:
        meta["term"] = term_num
        text = re.sub(TERM_PHRASE_RE, " ", text)

    # Part / copy marker like (2) - keep ALL markers verbatim so names like
    # "... (2) (2).pdf" or "... (2) (1785696829).pdf" round-trip stably.
    part_markers = PART_RE.findall(text)
    if part_markers:
        meta["part"] = " ".join(part_markers)
        text = re.sub(PART_RE, " ", text)

    # Grade: from filename first, then from the folder path
    grade, _ = detect_grade(raw_name)
    if grade is None:
        grade = _folder_grade(folder)
    if grade:
        meta["grade"] = grade
        text = re.sub(GRADE_TOKEN_RE, " ", text)
        text = re.sub(GRADE_PHRASE_RE, " ", text)
        text = re.sub(GRADE_NUM_RE, " ", text)

    # Series
    for pattern, label in SERIES_PATTERNS:
        if pattern.search(text):
            meta["series"] = label
            text = _remove_first(text, pattern)
            break

    # Subject
    for pattern, label in SUBJECT_PATTERNS:
        if pattern.search(text):
            meta["subject"] = label
            text = _remove_first(text, pattern)
            break

    # Publisher tag
    if PUBLISHER_RE.search(text):
        meta["publisher"] = "المتميزون"
        text = re.sub(PUBLISHER_RE, " ", text)

    leftover = re.sub(r"\s+", " ", text).strip(" _-")
    if leftover:
        meta["extra"] = leftover

    return meta


def build_target_name(meta: Dict, ext: str) -> str:
    """Builds the consistent Arabic-word target filename from metadata."""
    prefix = meta["type"] if meta["type"] in ("ملحق", "مراجعة", "حلول") else ""

    parts = []
    if meta["series"]:
        parts.append(meta["series"])
    if meta["subject"]:
        parts.append(meta["subject"])
    if meta["grade"]:
        parts.append(GRADE_ARABIC.get(meta["grade"], f"الصف {meta['grade']}"))
    if meta["term"]:
        parts.append(TERM_ARABIC.get(meta["term"], f"الترم {meta['term']}"))
    if meta["year"]:
        parts.append(str(meta["year"]))
    if meta["publisher"]:
        parts.append(meta["publisher"])
    if meta["extra"]:
        parts.append(meta["extra"])

    core = " - ".join(parts).strip()
    if meta["part"]:
        core = f"{core} {meta['part']}".strip()
    name = f"{prefix} {core}".strip() if prefix else core
    name = f"{name}.{ext}" if ext and not name.lower().endswith(f".{ext}") else name
    return sanitize_filename(name) or f"unidentified_book.{ext}"


def _json_safe(obj):
    """Recursively converts Path objects to strings for JSON serialization."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def write_catalog(records: List[Dict], csv_path: Path, json_path: Path):
    """Writes the metadata catalog as CSV (UTF-8 BOM) and JSON."""
    columns = [
        "index", "grade", "term", "year", "type", "series", "subject",
        "publisher", "part", "extra", "grade_arabic", "term_arabic",
        "old_filename", "new_filename", "old_path", "new_path",
        "chat_folder", "grade_folder", "size_bytes", "format", "duplicate",
        "size_duplicate",
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for rec in records:
            writer.writerow({c: rec.get(c, "") for c in columns})

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(records), f, ensure_ascii=False, indent=2)

    print(f"Catalog written: {csv_path}")
    print(f"Catalog written: {json_path}")


def _keep_priority(rec: Dict) -> Tuple:
    """Sort key for a byte-identical group: prefer keeping the cleanest copy."""
    name = rec["old_filename"]
    return (
        bool(re.search(r"\(\d+\)", name)),
        "المتميزون" in name,
        rec["old_path"],
    )


def dedup_by_size(records: List[Dict], apply: bool) -> List[Dict]:
    """Keeps one file per unique byte size and deletes identical-size extras.

    Two files with the exact same byte size are almost certainly the same file
    posted from different groups, even when their names differ slightly
    (e.g. a '- المتميزون' tag). Returns the surviving records. In dry-run mode
    the extras are kept but flagged; with apply=True they are deleted.
    """
    by_size: Dict[int, List[Dict]] = {}
    for rec in records:
        by_size.setdefault(rec["size_bytes"], []).append(rec)

    result: List[Dict] = []
    deleted = 0
    for size, group in by_size.items():
        if len(group) == 1:
            result.extend(group)
            continue
        group.sort(key=_keep_priority)
        result.append(group[0])
        for rec in group[1:]:
            rec["size_duplicate"] = True
            if not apply:
                result.append(rec)
                continue
            path = Path(rec["old_path"])
            try:
                path.unlink()
                deleted += 1
                print(f"  deleted duplicate (same size {size} bytes): {path.name}")
            except OSError as exc:
                print(f"  [warn] could not delete {path.name}: {exc}")
                result.append(rec)
    if deleted:
        print(f"Removed {deleted} duplicate file(s) with identical byte size.")
    return result


def check_and_purge_corrupted_pdfs(base_dir: Path) -> List[Path]:
    """Scans all PDF files in base_dir, verifies integrity with pypdf, deletes corrupted files."""
    corrupted_files = []
    pdf_files = [p for p in base_dir.rglob("*.pdf") if p.is_file()]
    if not pdf_files:
        return corrupted_files

    print(f"Checking {len(pdf_files)} PDF file(s) for integrity and corruption...")
    for pdf_path in pdf_files:
        is_corrupted = False
        try:
            if pdf_path.stat().st_size < 100:
                is_corrupted = True
            else:
                from pypdf import PdfReader
                reader = PdfReader(str(pdf_path))
                if reader.is_encrypted:
                    try:
                        reader.decrypt("")
                    except Exception:
                        is_corrupted = True
                num_pages = len(reader.pages)
                if num_pages == 0:
                    is_corrupted = True
                else:
                    _ = reader.pages[0]
        except Exception:
            is_corrupted = True

        if is_corrupted:
            try:
                pdf_path.unlink()
                corrupted_files.append(pdf_path)
                print(f"  [CORRUPTED PDF DELETED] Removed unreadable file: {pdf_path.name}")
            except OSError as exc:
                print(f"  [WARN] Failed to delete corrupted file {pdf_path.name}: {exc}")

    if corrupted_files:
        print(f"\n[!] Cleaned up {len(corrupted_files)} corrupted PDF file(s).")
        # Reset sync state so main.py re-scans missing files
        state_file = base_dir / ".download_state.json"
        if state_file.exists():
            try:
                state_file.unlink()
                print("  [STATE RESET] Incremental sync state reset to re-fetch missing books.")
            except OSError:
                pass
        print("=============================================================")
        print("  [NOTICE] Please run 'python main.py' to re-download missing books!")
        print("=============================================================\n")
    else:
        print("  [OK] PDF integrity check passed (no corrupted files found).\n")

    return corrupted_files


def rename_library(base_dir: Path, flat_dir: Optional[Path], csv_path: Path,
                   json_path: Path, apply: bool, dedup_size: bool = False) -> Optional[List[Dict]]:
    """Scans, parses, renames/flattens the library and writes the catalog.

    Returns the list of records, or None if no ebooks were found.
    """
    if apply:
        check_and_purge_corrupted_pdfs(base_dir)

    files = sorted(
        p for p in base_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTS
    )
    if not files:
        print(f"[!] No ebook files found under {base_dir}")
        return None

    records = []
    for idx, src in enumerate(files, start=1):
        rel = src.relative_to(base_dir).parts
        grade_folder = rel[0] if rel and rel[0].startswith("Grade") else ""
        chat_folder = rel[1] if len(rel) > 1 else ""

        meta = parse_book(src.stem, src.parent)
        ext = src.suffix.lower().lstrip(".")
        new_filename = build_target_name(meta, ext)

        records.append({
            "index": idx,
            **meta,
            "old_filename": src.name,
            "new_filename": new_filename,
            "old_path": str(src),
            "chat_folder": chat_folder,
            "grade_folder": grade_folder,
            "size_bytes": src.stat().st_size,
            "format": ext,
        })

    # Optional: drop byte-identical files (same file posted from more than one group)
    if dedup_size:
        records = dedup_by_size(records, apply)

    # Mark duplicates (same target base name appears more than once)
    name_counts = Counter(rec["new_filename"] for rec in records)
    for rec in records:
        rec["duplicate"] = name_counts[rec["new_filename"]] > 1

    # Resolve final destination paths + dedupe within the destination folder
    seen_targets: Dict[Path, int] = {}
    for rec in records:
        src = Path(rec["old_path"])
        if flat_dir:
            grade_num = rec.get("grade")
            grade_subfolder = f"Grade_{grade_num:02d}" if grade_num else "Grade_General"
            dest_dir = flat_dir / grade_subfolder
        else:
            dest_dir = src.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / rec["new_filename"]
        if target in seen_targets:
            seen_targets[target] += 1
            base = f"{target.stem} ({seen_targets[target]})"
            target = target.with_name(f"{base}{target.suffix}")
        else:
            seen_targets[target] = 1
        rec["new_path"] = str(target)
        rec["new_filename"] = target.name
        rec["target"] = target

    # Report
    print("=" * 70)
    print(f"Library scanned: {base_dir}  ({len(files)} ebooks)")
    print(f"Destination:    {flat_dir if flat_dir else 'in place'}")
    print("=" * 70)
    for rec in records:
        if rec.get("size_duplicate"):
            flag = "  [DUP-SIZE]"
        elif rec["duplicate"]:
            flag = "  [DUP]"
        else:
            flag = ""
        print(f"  {rec['index']:>2}. {rec['new_filename']}{flag}")

    # Catalog columns with readable Arabic grade/term
    for rec in records:
        rec["grade_arabic"] = GRADE_ARABIC.get(rec["grade"], "")
        rec["term_arabic"] = TERM_ARABIC.get(rec["term"], "")

    write_catalog(records, csv_path, json_path)

    if not apply:
        print("-" * 70)
        print("[DRY RUN] No files were changed. Re-run with --apply to rename/move.")
        return records

    # Apply: move/rename every file
    moved = skipped = 0
    for rec in records:
        src = Path(rec["old_path"])
        target = rec["target"]
        if src.resolve() == target.resolve():
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target = target.with_name(f"{target.stem} ({int(Path(rec['old_path']).stat().st_mtime)}){target.suffix}")
            rec["new_path"] = str(target)
        shutil.move(str(src), str(target))
        rec["new_path"] = str(target)
        moved += 1
        print(f"  moved: {src.name}\n      -> {target.name}")

    # Clean up empty folders left behind (but never the flat destination)
    removed_dirs = 0
    for dir_path in sorted(base_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not dir_path.is_dir():
            continue
        if flat_dir and dir_path.resolve() == flat_dir.resolve():
            continue
        try:
            if not any(dir_path.iterdir()):
                dir_path.rmdir()
                removed_dirs += 1
        except OSError:
            pass

    print("-" * 70)
    print(f"Done: {moved} file(s) renamed/moved, {skipped} already correct.")
    if removed_dirs:
        print(f"Removed {removed_dirs} empty folder(s).")
    print("Run the app again (or re-import the catalog) with the new library layout.")
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Rename the downloaded ebook library to a consistent Arabic schema, "
                    "flatten into one folder, and export a catalog for a database."
    )
    parser.add_argument("--dir", type=Path, default=None,
                        help="Library root to scan (default: OUTPUT_DIR from .env)")
    parser.add_argument("--flat-dir", type=Path, default=None,
                        help="Destination flat folder (default: <scan_dir>/library)")
    parser.add_argument("--no-flat", action="store_true",
                        help="Rename files in place instead of flattening into one folder")
    parser.add_argument("--apply", action="store_true",
                        help="Actually rename/move files (default is a dry run)")
    parser.add_argument("--dedupe", action="store_true",
                        help="Delete duplicate files with identical byte size (same file posted from more than one group)")
    parser.add_argument("--output-csv", type=Path, default=None,
                        help="CSV catalog path (default: <scan_dir>/books_catalog.csv)")
    parser.add_argument("--output-json", type=Path, default=None,
                        help="JSON catalog path (default: <scan_dir>/books_catalog.json)")
    args = parser.parse_args()

    base_dir = Path(args.dir) if args.dir else DownloaderConfig().output_dir
    if not base_dir.is_dir():
        print(f"[!] Directory not found: {base_dir}", file=sys.stderr)
        sys.exit(1)

    flat_dir = None
    if not args.no_flat:
        flat_dir = Path(args.flat_dir) if args.flat_dir else base_dir / "library"

    csv_path = args.output_csv or base_dir / "books_catalog.csv"
    json_path = args.output_json or base_dir / "books_catalog.json"

    records = rename_library(base_dir, flat_dir, csv_path, json_path, args.apply, args.dedupe)
    if records is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
