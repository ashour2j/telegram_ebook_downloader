import argparse
import sys
import asyncio
import logging
from pathlib import Path

from config import DownloaderConfig
from downloader import TelegramEbookDownloader


def parse_args() -> argparse.Namespace:
    """Parses command line arguments for the ebook downloader."""
    parser = argparse.ArgumentParser(
        description="Search and download ebook files (.pdf, .epub, .mobi, .azw3, .djvu) from Telegram channels, groups, or entire Telegram folders (classified by Grade 1 to Grade 12) with fast incremental library updates."
    )
    parser.add_argument("--api-id", type=int, help="Telegram API ID (or set TELEGRAM_API_ID in .env)")
    parser.add_argument("--api-hash", type=str, help="Telegram API Hash (or set TELEGRAM_API_HASH in .env)")
    parser.add_argument("--folder", "-f", type=str, help="Target Telegram folder name (e.g. 'School stuff') to scan all groups inside it")
    parser.add_argument("--target", "-t", type=str, help="Target single channel/group username or link (e.g. @ebooks_channel)")
    parser.add_argument("--grade", "-g", type=int, choices=range(1, 13), help="Filter downloads to a specific Grade (1 to 12). If omitted, downloads all grades.")
    parser.add_argument("--term", type=int, choices=(1, 2), help="Filter downloads to a specific school term (1 = first term, 2 = second term)")
    parser.add_argument("--full-sync", action="store_true", help="Force a full scan of all historical messages instead of fast incremental updates")
    parser.add_argument("--output-dir", "-o", type=str, help="Directory where downloaded ebooks will be saved (default: ./downloads)")
    parser.add_argument("--rename", action="store_true", help="Enable Regex template reformatting (default is to keep original filenames as-is)")
    parser.add_argument("--template", type=str, help="Output filename formatting template (default: '{title} - {author}.{ext}')")
    parser.add_argument("--pattern", "-p", action="append", help="Custom Regex pattern with named capture groups (can be specified multiple times)")
    parser.add_argument("--limit", "-l", type=int, help="Maximum number of messages to scan per group/channel")
    parser.add_argument("--reverse", action="store_true", help="Scan messages in reverse chronological order (oldest to newest)")
    parser.add_argument("--export-folder", action="store_true", help="Scrape usernames of all chats in the target folder and store them in .env (TELEGRAM_TARGET_CHAT)")
    return parser.parse_args()


async def main():
    args = parse_args()
    config = DownloaderConfig()

    if args.api_id:
        config.api_id = args.api_id
    if args.api_hash:
        config.api_hash = args.api_hash
    if args.folder:
        folder_val = args.folder
        config.target_folder = int(folder_val) if folder_val.isdigit() else folder_val
        config.target_chat = None
    elif args.target:
        config.target_chat = args.target
        config.target_folder = None

    # If a target_chat is provided, ignore any folder setting.
    if config.target_chat:
        logger = logging.getLogger(__name__)
        if config.target_folder:
            logger.info("Both TELEGRAM_TARGET_CHAT and TELEGRAM_TARGET_FOLDER are set; ignoring folder.")
        config.target_folder = None

    if args.grade:
        config.filter_grade = args.grade
    if args.term:
        config.filter_term = args.term
    if args.full_sync:
        config.update_mode = False
    if args.output_dir:
        config.output_dir = Path(args.output_dir)
    if args.rename:
        config.keep_original_filename = False
    if args.template:
        config.output_template = args.template
    if args.pattern:
        config.custom_patterns = args.pattern
    if args.limit:
        config.download_limit = args.limit
    if args.reverse:
        config.reverse_order = True

    if args.export_folder:
        exporter = TelegramEbookDownloader(config)
        await exporter.client.start()
        usernames = await exporter.get_usernames_from_folder()
        await exporter.client.disconnect()
        env_path = Path(__file__).parent / ".env"
        lines = env_path.read_text().splitlines()
        new_line = f"TELEGRAM_TARGET_CHAT={','.join(usernames)}"
        for i, line in enumerate(lines):
            if line.startswith('TELEGRAM_TARGET_CHAT='):
                lines[i] = new_line
                break
        else:
            lines.append(new_line)
        env_path.write_text("\n".join(lines) + "\n")
        logging.info(f"Exported {len(usernames)} usernames to .env")
        return
    else:
        try:
            downloader = TelegramEbookDownloader(config)
            await downloader.run()
        except KeyboardInterrupt:
            print("\n[!] Download interrupted by user. Exiting cleanly...")
        except Exception as e:
            print(f"\n[!] Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    asyncio.run(main())
