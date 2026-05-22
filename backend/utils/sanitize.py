"""
#49 — Input sanitization utilities.

Two layers of defense for user-submitted text:
1. Backend (this module): strip dangerous patterns + enforce limits at storage time
2. Frontend (separate): use textContent / proper escaping at render time
"""

import html
import re
from typing import Optional

_HTML_TAG_RE = re.compile(r'<[^>]+>')
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
_EXCESS_WHITESPACE_RE = re.compile(r'\s{3,}')

_DANGEROUS_URL_PROTOCOLS = (
    'javascript:',
    'data:text/html',
    'vbscript:',
    'file:',
)


def sanitize_text(value: Optional[str], max_length: int = 10000) -> str:
    """
    General-purpose text sanitizer. Strips HTML tags, control chars, and
    excessive whitespace. Enforces max length. Returns "" for None/empty.
    """
    if not value:
        return ""

    text = str(value)
    text = _HTML_TAG_RE.sub('', text)
    text = _CONTROL_CHARS_RE.sub('', text)
    text = _EXCESS_WHITESPACE_RE.sub(' ', text)
    text = text.strip()

    if len(text) > max_length:
        text = text[:max_length].rstrip()

    return text


def sanitize_title(value: Optional[str], max_length: int = 200) -> str:
    """Sanitize a title — single-line, max 200 chars."""
    if not value:
        return ""

    text = sanitize_text(value, max_length=max_length)
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) > max_length:
        text = text[:max_length].rstrip()

    return text


def sanitize_prompt(value: Optional[str], max_length: int = 2000) -> str:
    """Sanitize a system prompt / long-form text. Preserves newlines."""
    return sanitize_text(value, max_length=max_length)


def sanitize_email(value: Optional[str]) -> str:
    """Light email sanitization + format validation."""
    if not value:
        return ""

    email = str(value).strip().lower()

    if not re.match(r'^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$', email):
        return ""

    if len(email) > 254:
        return ""

    return email


def is_dangerous_url(value: Optional[str]) -> bool:
    """Check for dangerous URL protocols."""
    if not value:
        return False
    lowered = str(value).strip().lower()
    return any(lowered.startswith(proto) for proto in _DANGEROUS_URL_PROTOCOLS)


def escape_html(value: Optional[str]) -> str:
    """HTML-escape a string."""
    if not value:
        return ""
    return html.escape(str(value), quote=True)