import re
from typing import Optional, Dict, Tuple

from grade_parser import normalize_arabic_text

# Term labels for the Egyptian school system (الترم الأول / الترم الثاني)
TERM_DEFINITIONS: Dict[int, Tuple[str, str]] = {
    # First Term (الترم الأول)
    1: (
        "Term_1_First",
        r"(?:الترم|ترم)\s*(?:الاول|اول|الأول)\b|"
        r"الفصل\s*الدراسي\s*(?:الاول|اول|الأول)\b|"
        r"(?:الترم|ترم|ت)\s*1\b|\bت1\b|"
        r"\b(?:1st|first)\s*term\b|\bterm\s*1\b|\bsem(?:ester)?\s*1\b",
    ),
    # Second Term (الترم الثاني)
    2: (
        "Term_2_Second",
        r"(?:الترم|ترم)\s*(?:الثاني|التاني|الثانى|ثاني|تاني)\b|"
        r"الفصل\s*الدراسي\s*(?:الثاني|التاني|الثانى|ثاني|تاني)\b|"
        r"(?:الترم|ترم|ت)\s*2\b|\bت2\b|"
        r"\b(?:2nd|second)\s*term\b|\bterm\s*2\b|\bsem(?:ester)?\s*2\b",
    ),
}

COMPILED_TERM_PATTERNS = {
    term: (label, re.compile(raw_pattern, re.IGNORECASE))
    for term, (label, raw_pattern) in TERM_DEFINITIONS.items()
}


def detect_term(*texts: Optional[str]) -> Tuple[Optional[int], str]:
    """
    Scans input texts (filename, caption, group/channel name) to identify the
    school term (1 = first term / الترم الأول, 2 = second term / الترم الثاني).
    Returns a tuple of (term_number, term_label).
    """
    raw_combined = " ".join([t for t in texts if t]).strip()
    if not raw_combined:
        return None, "Term_Any"

    norm_combined = normalize_arabic_text(raw_combined)

    for term, (label, compiled_re) in COMPILED_TERM_PATTERNS.items():
        if compiled_re.search(norm_combined) or compiled_re.search(raw_combined):
            return term, label

    return None, "Term_Any"
