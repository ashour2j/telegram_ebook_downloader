# Telegram Ebook & Educational Library Downloader

A clean, modular Python application powered by [Telethon](https://github.com/LonamiWebs/Telethon) to automatically download educational ebooks (`.pdf`, `.epub`, `.mobi`, `.azw3`, `.djvu`) from Telegram channels, groups, or folders. Classified automatically by **Grade 1 to 12**, **School Term (1st / 2nd Term in Arabic)**, and **Year (e.g., 2027)** with real-time ETA, download resume support, and a non-terminal Desktop GUI.

---

## Key Features

1. **Desktop GUI App (`run_gui.bat` / `gui.py`)**:
   - Double-click desktop GUI for non-terminal users on Windows.
   - Configure targets, filters, start downloads, skip active files, and launch the invoice web app with one click.
2. **Arabic School Term Filtering (`FILTER_TERM=1` or `2`)**:
   - Filter downloads for **First Term** or **Second Term** in Arabic or English (`1st term`, `term 2`).
3. **Year Filtering (`FILTER_YEAR=2027`)**:
   - Limit downloads to specific curriculum years (e.g. `2027`).
4. **Resumable Downloads & Duplicate Checking**:
   - Uses `.part` temporary files to resume interrupted or partial downloads from the exact byte offset.
   - Skips files already downloaded or existing in the library.
5. **Real-time ETA & Progress Summary**:
   - Calculates download speed (`MB/s`) and remaining time (`ETA: MM:SS`).
   - Press **`Enter`** at any time while running to output a live `[PROGRESS SUMMARY]`.
6. **Robust Error Handling**:
   - Skips unresponding or invalid usernames gracefully with a clear notice (`[NOTICE] Username '@xyz' is not responding...`).
   - Press **`Ctrl+S`** to skip the currently downloading file.
7. **Organized Grade Folders**:
   - Running `python update_library.py` organizes all downloaded books into individual grade folders (`library/Grade_01`, `library/Grade_02`, ..., `library/Grade_12`).
8. **PDF Corruption Purging & Re-downloading**:
   - Running `python update_library.py` automatically checks all `.pdf` files for corruption, deletes unreadable files, and prompts `python main.py` to re-fetch clean copies.

---

## Quick Start Guide

### Desktop GUI (Non-Terminal Users)
Double-click `run_gui.bat` or run:
```bash
python gui.py
```

### Command Line (Terminal Users)
Run default download loop using `.env` settings:
```bash
python main.py
```

---

## Environment Configuration (`.env`)

```env
# Telegram Credentials
TELEGRAM_API_ID=YOUR_API_ID
TELEGRAM_API_HASH=YOUR_API_HASH

# Comma-separated list of target usernames
TELEGRAM_TARGET_CHAT=FahemnyKotob,G5_Y5,MAGFULLMARKG3

# Filters
FILTER_YEAR=2027
FILTER_TERM=1   # 1 = First Term, 2 = Second Term

# Output Directory
OUTPUT_DIR=./downloads/Books26-27
UPDATE_MODE=true
```

---

## Useful Commands

| Action | Command |
|---|---|
| Launch Desktop GUI | `python gui.py` or double-click `run_gui.bat` |
| Start Downloader (CLI) | `python main.py` |
| Download Specific Grade Only | `python main.py --grade 6` |
| Download Specific Term Only | `python main.py --term 1` |
| Organize Library & Rebuild DB | `python update_library.py` |
| Launch Invoice Web App | `python invoice_app.py` |
| Run Unit Tests | `python -m unittest discover` |

---

## Output Directory Structure

```
downloads/
├── Grade_01/
├── Grade_06/
├── Grade_12/
└── library/
    ├── Grade_01/
    ├── Grade_06/
    └── Grade_12/
```
