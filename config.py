import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set, Optional, Union
from dotenv import load_dotenv

# Automatically load environment variables from a .env file if available
load_dotenv()

@dataclass
class DownloaderConfig:
    """
    Configuration settings for Telegram Ebook Downloader.
    """
    api_id: int = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash: str = field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH", ""))
    
    # Target can be a single chat (@channel/link) OR a Telegram Folder name/ID
    target_chat: Optional[Union[str, int]] = field(
        default_factory=lambda: os.getenv("TELEGRAM_TARGET_CHAT", None)
    )
    target_folder: Optional[Union[str, int]] = field(
        default_factory=lambda: os.getenv("TELEGRAM_TARGET_FOLDER", None)
    )
    
    output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "./downloads"))
    )
    session_name: str = field(
        default_factory=lambda: os.getenv("SESSION_NAME", "ebook_downloader_session")
    )
    output_template: str = field(
        default_factory=lambda: os.getenv("OUTPUT_TEMPLATE", "{title} - {author}.{ext}")
    )
    allowed_extensions: Set[str] = field(
        default_factory=lambda: {"pdf", "epub", "mobi", "azw3", "djvu"}
    )
    custom_patterns: List[str] = field(default_factory=list)
    download_limit: Optional[int] = None
    reverse_order: bool = False
    
    # Keep original file names as-is
    keep_original_filename: bool = field(
        default_factory=lambda: os.getenv("KEEP_ORIGINAL_FILENAME", "true").lower() == "true"
    )
    
    # Automatically categorize downloaded files by Grade 1..12
    organize_by_grade: bool = True
    
    # Optional filter to only download a specific Grade (1..12)
    filter_grade: Optional[int] = None

    # Optional filter to only download a specific school term (1 = first term الترم الاول, 2 = second term الترم الثاني)
    filter_term: Optional[int] = field(
        default_factory=lambda: int(os.getenv("FILTER_TERM")) if os.getenv("FILTER_TERM") else None
    )

    # Only download books whose filename/caption/channel contains this year (e.g. 2027)
    filter_year: Optional[int] = field(
        default_factory=lambda: int(os.getenv("FILTER_YEAR")) if os.getenv("FILTER_YEAR") else None
    )

    # Incremental update mode: only fetch new messages posted since last run
    update_mode: bool = field(
        default_factory=lambda: os.getenv("UPDATE_MODE", "true").lower() == "true"
    )

    def validate(self):
        """Validates that essential API credentials and target options are set."""
        if not self.api_id or self.api_id == 0:
            raise ValueError(
                "TELEGRAM_API_ID is required. Set it in .env or pass it to DownloaderConfig."
            )
        if not self.api_hash or not self.api_hash.strip():
            raise ValueError(
                "TELEGRAM_API_HASH is required. Set it in .env or pass it to DownloaderConfig."
            )
        if not self.target_chat and not self.target_folder:
            raise ValueError(
                "Either TELEGRAM_TARGET_CHAT or TELEGRAM_TARGET_FOLDER must be set."
            )

        if self.filter_term is not None and self.filter_term not in (1, 2):
            raise ValueError("FILTER_TERM must be 1 (first term) or 2 (second term).")

        self.output_dir = Path(self.output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
