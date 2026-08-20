import re
from typing import Optional, Dict, Tuple, List

# Grade labels and patterns for grades 1 through 12
GRADE_DEFINITIONS: Dict[int, Tuple[str, str]] = {
    # Primary School (الابتدائي) - Grades 1 to 6
    1: ("Grade_01_Primary_1", r"1st\s*primary|grade\s*1|اولى\s*ابتدائي|الاول\s*الابتدائي|1\s*ابتدائي|1\s*ب\b|1ب"),
    2: ("Grade_02_Primary_2", r"2nd\s*primary|grade\s*2|ثانية\s*ابتدائي|تانية\s*ابتدائي|الثاني\s*الابتدائي|2\s*ابتدائي|2\s*ب\b|2ب"),
    3: ("Grade_03_Primary_3", r"3rd\s*primary|grade\s*3|ثالثة\s*ابتدائي|تالتة\s*ابتدائي|الثالث\s*الابتدائي|3\s*ابتدائي|3\s*ب\b|3ب"),
    4: ("Grade_04_Primary_4", r"4th\s*primary|grade\s*4|رابعة\s*ابتدائي|الرابع\s*الابتدائي|4\s*ابتدائي|4\s*ب\b|4ب"),
    5: ("Grade_05_Primary_5", r"5th\s*primary|grade\s*5|خامسة\s*ابتدائي|الخامس\s*الابتدائي|5\s*ابتدائي|5\s*ب\b|5ب"),
    6: ("Grade_06_Primary_6", r"6th\s*primary|grade\s*6|سادسة\s*ابتدائي|السادس\s*الابتدائي|6\s*ابتدائي|6\s*ب\b|6ب"),

    # Middle / Prep School (الإعدادي) - Grades 7 to 9
    7: ("Grade_07_Prep_1", r"1st\s*prep|grade\s*7|اولى\s*اعدادي|الاول\s*الاعدادي|1\s*اعدادي|1\s*ع\b|1ع"),
    8: ("Grade_08_Prep_2", r"2nd\s*prep|grade\s*8|ثانية\s*اعدادي|تانية\s*اعدادي|الثاني\s*الاعدادي|2\s*اعدادي|2\s*ع\b|2ع"),
    9: ("Grade_09_Prep_3", r"3rd\s*prep|grade\s*9|ثالثة\s*اعدادي|تالتة\s*اعدادي|الثالث\s*الاعدادي|3\s*اعدادي|3\s*ع\b|3ع"),

    # Secondary School (الثانوي) - Grades 10 to 12
    10: ("Grade_10_Sec_1", r"1st\s*sec|grade\s*10|اولى\s*ثانوي|الاول\s*الثانوي|1\s*ثانوي|1\s*ث\b|1ث"),
    11: ("Grade_11_Sec_2", r"2nd\s*sec|grade\s*11|ثانية\s*ثانوي|تانية\s*ثانوي|الثاني\s*الثانوي|2\s*ثانوي|2\s*ث\b|2ث"),
    12: ("Grade_12_Sec_3", r"3rd\s*sec|grade\s*12|ثالثة\s*ثانوي|تالتة\s*ثانوي|الثالث\s*الثانوي|3\s*ثانوي|3\s*ث\b|3ث"),
}

COMPILED_PATTERNS = {
    grade: (label, re.compile(raw_pattern, re.IGNORECASE))
    for grade, (label, raw_pattern) in GRADE_DEFINITIONS.items()
}

def normalize_arabic_text(text: str) -> str:
    """Normalizes Arabic letters (alefs, yas, tah marbutas) for consistent regex matching."""
    if not text:
        return ""
    
    # Replace underscores and hyphens with spaces for boundary handling
    t = text.replace('_', ' ').replace('-', ' ')
    
    # Standardize letters
    t = re.sub(r'[أإآ]', 'ا', t)
    t = t.replace('ى', 'ي')
    t = t.replace('ة', 'ه')
    
    # Remove Arabic diacritics (tashkeel)
    t = re.sub(r'[\u064B-\u0652]', '', t)
    return t.strip()

def detect_grade(*texts: Optional[str]) -> Tuple[Optional[int], str]:
    """
    Scans input texts (filename, caption, group/channel name) to identify the educational grade (1 to 12).
    Returns a tuple of (grade_number, grade_folder_label).
    """
    raw_combined = " ".join([t for t in texts if t]).strip()
    if not raw_combined:
        return None, "General_Books"

    norm_combined = normalize_arabic_text(raw_combined)

    for grade, (label, compiled_re) in COMPILED_PATTERNS.items():
        if compiled_re.search(norm_combined) or compiled_re.search(raw_combined):
            return grade, label

    return None, "General_Books"
