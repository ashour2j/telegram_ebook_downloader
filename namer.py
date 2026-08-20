import os
import re
import mimetypes
from typing import List, Dict, Optional, Tuple

# Common ebook MIME types mapping
MIME_TO_EXT = {
    'application/pdf': 'pdf',
    'application/epub+zip': 'epub',
    'application/x-mobipocket-ebook': 'mobi',
    'application/vnd.amazon.mobi8-ebook': 'azw3',
    'image/vnd.djvu': 'djvu',
    'image/x-djvu': 'djvu',
}

DEFAULT_PATTERNS = [
    # "Title - Author.ext" or "Title - Author"
    r"^(?P<title>.+?)\s*-\s*(?P<author>.+?)(?:\.(?P<ext>pdf|epub|mobi|azw3|djvu))?$",
    # "Title by Author.ext" or "Title by Author"
    r"^(?P<title>.+?)\s+by\s+(?P<author>.+?)(?:\.(?P<ext>pdf|epub|mobi|azw3|djvu))?$",
    # "Title_Author.ext" or "Title_Author"
    r"^(?P<title>[^\_]+)_(?P<author>.+?)(?:\.(?P<ext>pdf|epub|mobi|azw3|djvu))?$",
    # "[Author] Title.ext"
    r"^\[(?P<author>[^\]]+)\]\s*(?P<title>.+?)(?:\.(?P<ext>pdf|epub|mobi|azw3|djvu))?$",
]

def sanitize_filename(name: str) -> str:
    """Removes invalid OS filename characters for cross-platform compatibility."""
    if not name:
        return ""
    # Strip illegal OS characters: < > : " / \ | ? *
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Normalize multiple whitespace characters
    cleaned = re.sub(r'\s+', ' ', cleaned).strip('. ')
    return cleaned

class FilenameFormatter:
    """
    Parses raw filenames/captions using customizable regex templates with
    named capture groups and formats them into standardized output filenames.
    """
    def __init__(
        self,
        patterns: Optional[List[str]] = None,
        output_template: str = "{title} - {author}.{ext}",
        allowed_extensions: Optional[set] = None,
        keep_original: bool = False
    ):
        pattern_list = patterns if patterns is not None else DEFAULT_PATTERNS
        self.patterns = [re.compile(p, re.IGNORECASE) for p in pattern_list]
        self.output_template = output_template
        self.allowed_extensions = allowed_extensions or {"pdf", "epub", "mobi", "azw3", "djvu"}
        self.keep_original = keep_original

    def get_extension(
        self,
        raw_filename: Optional[str],
        mime_type: Optional[str],
        caption: Optional[str]
    ) -> str:
        """Extracts and validates ebook file extension from filename, MIME type, or caption."""
        # 1. From raw filename
        if raw_filename and '.' in raw_filename:
            ext = raw_filename.rsplit('.', 1)[-1].lower().strip()
            if ext in self.allowed_extensions:
                return ext

        # 2. From MIME type
        if mime_type:
            mime_low = mime_type.lower()
            if mime_low in MIME_TO_EXT:
                return MIME_TO_EXT[mime_low]
            guessed = mimetypes.guess_extension(mime_low)
            if guessed:
                ext = guessed.lstrip('.').lower()
                if ext in self.allowed_extensions:
                    return ext

        # 3. From caption text regex
        if caption:
            match = re.search(r'\.(pdf|epub|mobi|azw3|djvu)\b', caption, re.IGNORECASE)
            if match:
                return match.group(1).lower()

        return ""

    def parse_and_format(self, raw_name: str, ext: str) -> Tuple[str, bool]:
        """
        Parses raw_name against regex patterns.
        Returns tuple of (formatted_filename, is_pattern_matched).
        """
        # Strip extension from raw_name if present to normalize base_name
        base_name = raw_name
        if ext and base_name.lower().endswith(f".{ext}"):
            base_name = base_name[:-len(ext) - 1]

        base_name = base_name.strip()

        # If user explicitly requested keeping original raw names as-is
        if self.keep_original:
            clean_base = sanitize_filename(base_name) or "untitled_ebook"
            return f"{clean_base}.{ext}" if ext else clean_base, False

        for pattern in self.patterns:
            match = pattern.match(raw_name) or pattern.match(base_name)
            if match:
                groups = match.groupdict()
                if not groups.get("ext"):
                    groups["ext"] = ext

                # Sanitize extracted values
                sanitized_groups = {k: sanitize_filename(v) if v else "" for k, v in groups.items()}

                # Fallback if both title and author are empty
                if not sanitized_groups.get("title") and not sanitized_groups.get("author"):
                    continue

                try:
                    formatted_name = self.output_template.format(**sanitized_groups)
                    # Append extension if missing from output template
                    if ext and not formatted_name.lower().endswith(f".{ext}"):
                        formatted_name = f"{formatted_name}.{ext}"
                    return sanitize_filename(formatted_name), True
                except KeyError:
                    # Template field mismatch with group names
                    pass

        # Fallback: clean raw name directly without skipping
        clean_base = sanitize_filename(base_name) or "untitled_ebook"
        fallback_name = f"{clean_base}.{ext}" if ext else clean_base
        return fallback_name, False
