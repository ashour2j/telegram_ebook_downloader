import os
import sys
import logging
import asyncio
import threading
import time
from pathlib import Path
from typing import Optional, Union, List, Tuple, Set

from telethon import TelegramClient
from telethon.tl.types import Message, MessageMediaDocument, DocumentAttributeFilename, DialogFilter
from telethon.tl.functions.messages import GetDialogFiltersRequest

from config import DownloaderConfig
from namer import FilenameFormatter, sanitize_filename
from grade_parser import detect_grade
from term_parser import detect_term
from state_manager import StateManager


class DownloadSkipped(Exception):
    """Raised when the user presses Ctrl+S to skip the current download."""
    pass


# Configure colorful and structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("EbookDownloader")


class TelegramEbookDownloader:
    """
    Downloads ebook files from Telegram channels/groups or entire Telegram Folders,
    automatically searching, classifying, organizing by Grade 1..12, and
    supporting instant incremental library updates.
    """
    def __init__(self, config: DownloaderConfig):
        self.config = config
        self.config.validate()
        
        self.formatter = FilenameFormatter(
            patterns=self.config.custom_patterns or None,
            output_template=self.config.output_template,
            allowed_extensions=self.config.allowed_extensions,
            keep_original=self.config.keep_original_filename
        )
        self.client = TelegramClient(
            self.config.session_name,
            self.config.api_id,
            self.config.api_hash
        )
        self.state_manager = StateManager(self.config.output_dir / ".download_state.json")
        self._skip_event = threading.Event()
        self._downloading = threading.Event()

        self.stats = {
            "total_targets": 0,
            "current_target_index": 0,
            "current_target_name": "",
            "messages_scanned": 0,
            "files_downloaded": 0,
            "bytes_downloaded": 0,
            "files_skipped": 0,
            "current_filename": "",
            "current_file_downloaded": 0,
            "current_file_total": 0,
        }

    def _is_already_downloaded(self, target_path: Path, doc_size: int) -> bool:
        """Return True if the file exists and matches the expected size."""
        if target_path.is_file():
            existing_size = target_path.stat().st_size
            return existing_size == doc_size
        return False

    def _scan_library_sizes(self) -> Set[int]:
        """Scans the output directory and collects all existing file sizes in bytes."""
        sizes = set()
        if self.config.output_dir.exists():
            for p in self.config.output_dir.rglob("*"):
                if p.is_file() and p.name != ".download_state.json":
                    try:
                        sizes.add(p.stat().st_size)
                    except OSError:
                        pass
        return sizes

    def _extract_raw_filename_and_mime(self, message: Message) -> Tuple[Optional[str], Optional[str]]:
        """Extracts document filename attribute and MIME type from a Telegram message."""
        if not message.media or not isinstance(message.media, MessageMediaDocument):
            return None, None

        doc = message.media.document
        mime_type = doc.mime_type
        raw_filename = None

        if doc.attributes:
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    raw_filename = attr.file_name
                    break

        return raw_filename, mime_type

    def _print_progress_summary(self):
        """Displays a clean progress summary when user presses Enter."""
        cur_file = self.stats.get("current_filename")
        cur_dl = self.stats.get("current_file_downloaded", 0)
        cur_tot = self.stats.get("current_file_total", 0)
        active_str = ""
        if cur_file and cur_tot > 0:
            pct = (cur_dl / cur_tot) * 100
            mb_dl = cur_dl / (1024 * 1024)
            mb_tot = cur_tot / (1024 * 1024)
            active_str = f"\n  Active File: '{cur_file}' ({pct:.1f}% - {mb_dl:.1f}/{mb_tot:.1f} MB)"

        tot_mb = self.stats.get("bytes_downloaded", 0) / (1024 * 1024)
        logger.info(
            f"\n==================== [PROGRESS SUMMARY] ====================\n"
            f"  Target Chat: [{self.stats.get('current_target_index', 0)}/{self.stats.get('total_targets', 0)}] '{self.stats.get('current_target_name', 'N/A')}'\n"
            f"  Messages Scanned: {self.stats.get('messages_scanned', 0)}\n"
            f"  Files Downloaded: {self.stats.get('files_downloaded', 0)} ({tot_mb:.2f} MB total)\n"
            f"  Files Skipped: {self.stats.get('files_skipped', 0)}{active_str}\n"
            f"============================================================"
        )

    def _progress_callback(self, filename: str, offset_bytes: int = 0):
        """Creates a download progress callback with speed & ETA calculation + Ctrl+S skip."""
        last_percent = [-1]
        start_time = time.time()
        last_log_time = [start_time]

        def callback(current: int, total: int):
            actual_current = offset_bytes + current
            actual_total = offset_bytes + total if total > 0 else 0

            self.stats["current_filename"] = filename
            self.stats["current_file_downloaded"] = actual_current
            self.stats["current_file_total"] = actual_total

            if self._skip_event.is_set():
                raise DownloadSkipped(filename)
            if actual_total <= 0:
                return

            now = time.time()
            percent = int((actual_current / actual_total) * 100)

            if (percent != last_percent[0] and (percent % 10 == 0 or percent == 100)) or (now - last_log_time[0] >= 3.0):
                last_percent[0] = percent
                last_log_time[0] = now
                elapsed = now - start_time
                speed = current / elapsed if elapsed > 0 else 0
                speed_str = f"{speed / (1024*1024):.2f} MB/s" if speed >= 1024*1024 else f"{speed / 1024:.1f} KB/s"
                remaining_bytes = actual_total - actual_current
                eta_sec = int(remaining_bytes / speed) if speed > 0 else 0
                eta_min, eta_s = divmod(eta_sec, 60)
                eta_str = f"{eta_min:02d}:{eta_s:02d}"

                current_mb = actual_current / (1024 * 1024)
                total_mb = actual_total / (1024 * 1024)
                logger.info(
                    f"Downloading '{filename}': {percent}% "
                    f"({current_mb:.1f}/{total_mb:.1f} MB) | Speed: {speed_str} | ETA: {eta_str}"
                )

        return callback

    def _start_keyboard_listener(self):
        """Daemon thread listening for Ctrl+S (skip current download) and Enter (show progress summary)."""
        def _listener():
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    while True:
                        if msvcrt.kbhit():
                            ch = msvcrt.getch()
                            if ch == b'\x13':  # Ctrl+S
                                if self._downloading.is_set():
                                    self._skip_event.set()
                                    logger.warning("[SKIP] Ctrl+S detected — skipping current download...")
                            elif ch in (b'\r', b'\n'):  # Enter key
                                self._print_progress_summary()
                        time.sleep(0.05)
                else:
                    import select, termios, tty
                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)
                    try:
                        tty.setcbreak(fd)
                        while True:
                            if select.select([sys.stdin], [], [], 0.05)[0]:
                                ch = sys.stdin.read(1)
                                if ch == '\x13':  # Ctrl+S
                                    if self._downloading.is_set():
                                        self._skip_event.set()
                                        logger.warning("[SKIP] Ctrl+S detected — skipping current download...")
                                elif ch in ('\r', '\n'):  # Enter key
                                    self._print_progress_summary()
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass

        t = threading.Thread(target=_listener, daemon=True, name="keyboard-listener")
        t.start()

    async def _resolve_targets(self) -> List[Tuple[str, any]]:
        """
        Resolves list of target chats to scan.
        Supports single chat targets, comma-separated target list, or Telegram folders.
        Skips invalid/unresponding usernames gracefully with a notice.
        """
        targets = []

        if self.config.target_folder:
            logger.info(f"Fetching Telegram chat folders to locate: '{self.config.target_folder}'...")
            try:
                dialog_filters = await self.client(GetDialogFiltersRequest())
                target_filter = None
                available_folders = []

                for d_filter in dialog_filters.filters:
                    if isinstance(d_filter, DialogFilter):
                        available_folders.append(f"'{d_filter.title}' (ID: {d_filter.id})")
                        folder_id_match = False
                        if isinstance(self.config.target_folder, int):
                            folder_id_match = d_filter.id == self.config.target_folder
                        else:
                            if str(self.config.target_folder).isdigit():
                                folder_id_match = d_filter.id == int(self.config.target_folder)
                        if folder_id_match:
                            target_filter = d_filter
                        elif str(d_filter.title).strip().lower() == str(self.config.target_folder).strip().lower():
                            target_filter = d_filter

                if not target_filter:
                    logger.error(f"Folder '{self.config.target_folder}' not found!")
                    logger.info(f"Available folders in your Telegram account: {', '.join(available_folders)}")
                    raise ValueError(f"Folder '{self.config.target_folder}' not found.")

                logger.info(f"Found Folder: '{target_filter.title}' (Folder ID: {target_filter.id})")
                from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser
                include_ids = set()
                for peer in getattr(target_filter, "include_peers", []):
                    if isinstance(peer, InputPeerChannel):
                        include_ids.add(peer.channel_id)
                    elif isinstance(peer, InputPeerChat):
                        include_ids.add(peer.chat_id)
                    elif isinstance(peer, InputPeerUser):
                        include_ids.add(peer.user_id)
                async for dialog in self.client.iter_dialogs():
                    entity_id = getattr(dialog.entity, "id", None)
                    if include_ids:
                        if entity_id in include_ids:
                            targets.append((dialog.name, dialog.entity))
                    else:
                        if getattr(dialog, "folder_id", None) == target_filter.id:
                            targets.append((dialog.name, dialog.entity))
                if not targets:
                    logger.warning(f"Folder '{target_filter.title}' contains no chats. Scanning all dialogs instead.")
                    async for dialog in self.client.iter_dialogs():
                        targets.append((dialog.name, dialog.entity))
            except Exception as exc:
                logger.warning(f"[NOTICE] Folder '{self.config.target_folder}' could not be accessed ({exc}).")

        elif isinstance(self.config.target_chat, str) and "," in self.config.target_chat:
            usernames = [u.strip() for u in self.config.target_chat.split(',') if u.strip()]
            for uname in usernames:
                try:
                    entity = await self.client.get_entity(uname)
                    chat_name = getattr(entity, "title", getattr(entity, "username", uname))
                    targets.append((chat_name, entity))
                except Exception as exc:
                    logger.warning(f"[NOTICE] Username '{uname}' is not responding or not found ({exc}). Skipping to next target...")
                    continue
        elif self.config.target_chat:
            try:
                entity = await self.client.get_entity(self.config.target_chat)
                chat_name = getattr(entity, 'title', getattr(entity, 'username', str(self.config.target_chat)))
                targets.append((chat_name, entity))
            except Exception as exc:
                logger.warning(f"[NOTICE] Target '{self.config.target_chat}' is not responding or not found ({exc}). Skipping...")

        return targets

    async def get_usernames_from_folder(self) -> list[str]:
        """Return a list of usernames for chats inside the configured folder."""
        targets = await self._resolve_targets()
        usernames: list[str] = []
        for _name, entity in targets:
            username = getattr(entity, "username", None)
            if username:
                usernames.append(username)
        return usernames

    async def run(self):
        """Connects to Telegram client and initiates scanning, grade matching, & incremental downloads."""
        logger.info(f"Starting Telegram Client session: {self.config.session_name}")
        await self.client.start()
        self._start_keyboard_listener()
        logger.info("Press Ctrl+S to skip active download | Press Enter to see live progress summary.")
        
        me = await self.client.get_me()
        logger.info(f"Logged in as: {me.first_name} (@{me.username or me.id})")
        if self.config.filter_year:
            logger.info(f"Year filter active: only downloading books matching '{self.config.filter_year}'")
        if self.config.filter_term:
            term_str = "First Term (الترم الأول)" if self.config.filter_term == 1 else "Second Term (الترم الثاني)"
            logger.info(f"Term filter active: only downloading books matching '{term_str}'")
        
        target_chats = await self._resolve_targets()
        
        if not target_chats:
            logger.warning("No target chats or groups found to scan.")
            return

        self._library_sizes = self._scan_library_sizes()
        logger.info(f"Library size index: {len(self._library_sizes)} unique file size(s) found.")

        self.stats["total_targets"] = len(target_chats)

        grand_total_scanned = 0
        grand_total_downloaded = 0
        grand_total_skipped = 0

        for idx, (chat_name, chat_entity) in enumerate(target_chats, start=1):
            self.stats["current_target_index"] = idx
            self.stats["current_target_name"] = chat_name

            clean_chat_name = sanitize_filename(chat_name)
            logger.info("=" * 60)
            logger.info(f"[{idx}/{len(target_chats)}] Scanning Group/Channel: '{chat_name}'")

            last_msg_id = None
            if self.config.update_mode:
                last_msg_id = self.state_manager.get_last_message_id(chat_name)
                if last_msg_id:
                    logger.info(f"[INCREMENTAL SYNC] Fast-updating library! Checking only new messages after ID #{last_msg_id}...")
                else:
                    logger.info("[FULL SYNC] First run for this group. Scanning full message history...")

            logger.info("=" * 60)

            scanned = 0
            downloaded = 0
            skipped = 0
            max_msg_id_seen = last_msg_id or 0

            iter_kwargs = {
                "limit": self.config.download_limit,
                "reverse": self.config.reverse_order
            }
            if self.config.update_mode and last_msg_id:
                iter_kwargs["min_id"] = last_msg_id

            try:
                async for message in self.client.iter_messages(chat_entity, **iter_kwargs):
                    if message.id > max_msg_id_seen:
                        max_msg_id_seen = message.id

                    if not message.media or not isinstance(message.media, MessageMediaDocument):
                        continue

                    doc = message.media.document
                    doc_size = doc.size if doc else 0
                    caption = message.text or ""

                    raw_filename, mime_type = self._extract_raw_filename_and_mime(message)

                    candidate_name = raw_filename or (caption.split('\n')[0].strip() if caption else f"document_{message.id}")
                    ext = self.formatter.get_extension(raw_filename, mime_type, caption)
                    
                    if not ext or ext not in self.config.allowed_extensions:
                        continue

                    scanned += 1
                    self.stats["messages_scanned"] += 1

                    # Detect Grade (1..12) from channel name, caption, or filename
                    grade_num, grade_label = detect_grade(chat_name, caption, candidate_name)

                    # Grade filter check if requested by user
                    if self.config.filter_grade and grade_num != self.config.filter_grade:
                        logger.debug(f"Skipping msg #{message.id}: Grade {grade_num} does not match filter (Grade {self.config.filter_grade})")
                        continue

                    # Year filter check (e.g. only download 2027 books)
                    if self.config.filter_year:
                        year_str = str(self.config.filter_year)
                        if year_str not in candidate_name and year_str not in caption and year_str not in chat_name:
                            logger.debug(f"Skipping msg #{message.id}: '{candidate_name}' does not match year filter ({year_str})")
                            continue

                    # Term filter check (first term / second term)
                    if self.config.filter_term:
                        term_num, term_label = detect_term(chat_name, caption, candidate_name)
                        if term_num != self.config.filter_term:
                            logger.debug(f"Skipping msg #{message.id}: Term '{term_label}' ({term_num}) does not match filter (Term {self.config.filter_term})")
                            continue

                    # Determine destination folder (Organize into Grade_XX folder)
                    if self.config.organize_by_grade:
                        dest_dir = self.config.output_dir / grade_label / clean_chat_name
                    else:
                        dest_dir = self.config.output_dir / clean_chat_name

                    dest_dir.mkdir(parents=True, exist_ok=True)

                    target_filename, pattern_matched = self.formatter.parse_and_format(candidate_name, ext)
                    target_path = dest_dir / target_filename
                    part_path = dest_dir / f"{target_filename}.part"

                    # Already fully downloaded check
                    if target_path.exists() and target_path.stat().st_size == doc_size:
                        logger.info(f"[SKIP] Already downloaded: '{target_filename}' ({doc_size} bytes)")
                        skipped += 1
                        self.stats["files_skipped"] += 1
                        continue
                    elif doc_size in self._library_sizes:
                        logger.info(f"[SKIP] Already in library (same size in another group): '{target_filename}' ({doc_size} bytes)")
                        skipped += 1
                        self.stats["files_skipped"] += 1
                        continue

                    # Download / Resume logic
                    try:
                        self._skip_event.clear()
                        self._downloading.set()

                        existing_bytes = 0
                        if part_path.exists():
                            existing_bytes = part_path.stat().st_size
                        elif target_path.exists() and target_path.stat().st_size < doc_size:
                            target_path.rename(part_path)
                            existing_bytes = part_path.stat().st_size

                        if existing_bytes > 0 and existing_bytes < doc_size:
                            logger.info(f"[RESUME DOWNLOAD] Resuming '{target_filename}' from {existing_bytes / (1024*1024):.1f} MB / {doc_size / (1024*1024):.1f} MB...")
                            with open(part_path, "ab") as f:
                                await self.client.download_file(
                                    message.media.document,
                                    file=f,
                                    offset=existing_bytes,
                                    progress_callback=self._progress_callback(target_filename, offset_bytes=existing_bytes)
                                )
                        else:
                            logger.info(f"[START DOWNLOAD] Saving to '{grade_label}' -> '{target_filename}' ({doc_size} bytes)...")
                            await self.client.download_media(
                                message,
                                file=str(part_path),
                                progress_callback=self._progress_callback(target_filename)
                            )

                        if part_path.exists():
                            if target_path.exists():
                                target_path.unlink()
                            part_path.rename(target_path)

                        self._downloading.clear()
                        self._library_sizes.add(doc_size)
                        downloaded += 1
                        self.stats["files_downloaded"] += 1
                        self.stats["bytes_downloaded"] += doc_size
                        self.stats["current_filename"] = ""
                        logger.info(f"[SUCCESS] Saved to '{target_path.relative_to(self.config.output_dir)}'\n")
                    except DownloadSkipped:
                        self._downloading.clear()
                        skipped += 1
                        self.stats["files_skipped"] += 1
                        self.stats["current_filename"] = ""
                        logger.info(f"[SKIPPED] Download of '{target_filename}' skipped by user.")
                        continue
                    except Exception as exc:
                        self._downloading.clear()
                        logger.error(f"[ERROR] Failed downloading '{target_filename}': {exc}")
                        continue
            except Exception as chat_exc:
                logger.warning(f"[NOTICE] Failed or lost connection to group '{chat_name}': {chat_exc}. Skipping to next group...")
                continue

            # Update highest processed message ID for incremental updates
            if max_msg_id_seen > (last_msg_id or 0):
                self.state_manager.update_last_message_id(chat_name, max_msg_id_seen)

            grand_total_scanned += scanned
            grand_total_downloaded += downloaded
            grand_total_skipped += skipped

        logger.info("=" * 60)
        logger.info(f"Library Update Completed!")
        logger.info(f"Groups/Channels Processed: {len(target_chats)}")
        logger.info(f"Total Scanned Ebooks: {grand_total_scanned}")
        logger.info(f"Total Downloaded New Books: {grand_total_downloaded}")
        logger.info(f"Total Skipped (Already in Library): {grand_total_skipped}")
        logger.info("=" * 60)

    async def close(self):
        """Disconnects the client session."""
        await self.client.disconnect()
