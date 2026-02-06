# app/security.py

import re
import unicodedata
from typing import List, Tuple

# Patterns that could be used for prompt injection or to confuse the LLM
INJECTION_PATTERNS = [
    r"(?i)System:", 
    r"(?i)Human:", 
    r"(?i)Assistant:", 
    r"(?i)AI:", 
    r"(?i)Admin:",
    r"(?i)user:",
    r"\[INST\]", 
    r"\[/INST\]", 
    r"<<SYS>>", 
    r"<</SYS>>",
    r"(?i)ignore\s+(previous|above|all)\s+instructions",
    r"(?i)disregard\s+(previous|above|all)\s+(instructions|rules)",
    r"(?i)forget\s+(previous|above|everything)",
    r"(?i)you are now a",
    r"(?i)system prompt",
    r"(?i)do anything now",  # DAN jailbreak
    r"(?i)jailbreak",
    r"(?i)bypass\s+(security|filter|rules)",
]


def detect_injection_patterns(text: str) -> list[str]:
    """
    Returns a list of detected injection pattern names.
    Used to block queries before they reach the LLM.
    """
    detected = []
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text):
            detected.append(pattern)
    return detected

# Invisible or confusing unicode ranges
SUSPICIOUS_UNICODE_RANGES = [
    (0x200B, 0x200D),  # Zero-width characters
    (0x2028, 0x202F),  # Line/paragraph separators, embedding controls
    (0x2060, 0x206F),  # Word joiner, invisible operators
    (0xFEFF, 0xFEFF),  # BOM (zero-width no-break space)
    (0xFFF0, 0xFFFF),  # Specials block
]

# Comprehensive emoji and pictograph pattern
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "\U0001F780-\U0001F7FF"  # geometric shapes extended
    "\U0001F800-\U0001F8FF"  # supplemental arrows-C
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U00002702-\U000027B0"  # dingbats
    "\U0001F1E0-\U0001F1FF"  # flags
    "]+", 
    flags=re.UNICODE
)

def sanitize_text(text: str, strict_ascii: bool = False, max_length: int = 5000) -> str:
    """
    Hyper-hardened sanitization for clinical text and AI queries.
    
    1. Strips non-printable and suspicious unicode.
    2. Strips emojis.
    3. Strips prompt injection triggers.
    4. Normalizes whitespace.
    5. Enforces length limits.
    """
    if not text:
        return ""

    # 1. Truncate to prevent DoS
    sanitized = text[:max_length]

    # 2. Remove invisible/zero-width characters and controls
    cleaned_chars = []
    for char in sanitized:
        code_point = ord(char)
        is_suspicious = any(start <= code_point <= end for start, end in SUSPICIOUS_UNICODE_RANGES)
        is_control = unicodedata.category(char).startswith('C') and char not in "\n\r\t"
        
        if not (is_suspicious or is_control):
            cleaned_chars.append(char)
    sanitized = "".join(cleaned_chars)

    # 3. Strip Emojis
    sanitized = EMOJI_PATTERN.sub('', sanitized)

    # 4. Strip Injection Tags
    for pattern in INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[REDACTED]", sanitized)

    # 5. Strict ASCII (Optional, e.g. for HL7)
    if strict_ascii:
        sanitized = sanitized.encode('ascii', 'ignore').decode('ascii')

    # 6. Normalize Whitespace (unless it's HL7 where it might matter, but usually collapses fine)
    if not strict_ascii:
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    else:
        # For HL7, keep segments distinct but clean trailing spaces
        sanitized = sanitized.strip()

    return sanitized
