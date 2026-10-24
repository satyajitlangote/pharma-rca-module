"""Evidence verification — NON-NEGOTIABLE accuracy principle #5.

An AI claim gets status "Supported" ONLY when its quote can be located in the
source document *by this code* (normalized substring first, then a fuzzy
token-window match). Anything else stays "Hypothesis". There is intentionally
no path to a "Verified" status: verification always requires a QP sign-off.

The same helpers verify extracted values (principle #1): a value that cannot be
located in the document is dropped and reported as "Not stated in document".
"""
from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher

_WS = re.compile(r"[\s\u00a0]+")
_TRAILING_PUNCT = re.compile(r"[.,;:!?\"']+$")

# Acceptable fuzzy containment ratio for quotes (near-verbatim).
QUOTE_MIN_RATIO = 0.90
# Slightly looser for long free-text values (description, containment, ...).
VALUE_MIN_RATIO = 0.85


def normalize(text: str) -> str:
    """Lowercase, unify smart quotes/dashes, collapse whitespace, trim punctuation.

    Used for every comparison so a quote copied from a PDF with different
    whitespace/quotes still counts as present.
    """
    t = (text or "").lower()
    for a, b in (
        ("\u2018", "'"), ("\u2019", "'"),
        ("\u201c", '"'), ("\u201d", '"'),
        ("\u2013", "-"), ("\u2014", "-"),
        ("\u00a0", " "),
    ):
        t = t.replace(a, b)
    t = _WS.sub(" ", t).strip()
    return _TRAILING_PUNCT.sub("", t)


def _fuzzy_contains(normalized_needle: str, normalized_haystack: str, min_ratio: float) -> bool:
    """Token-window fuzzy containment.

    Strategy: anchor on a distinctive token of the needle, align a window of
    needle tokens at that position, and compare with SequenceMatcher. This
    tolerates small OCR/typing differences but fails for fabricated text.
    """
    needle_tokens = normalized_needle.split()
    hay_tokens = normalized_haystack.split()
    n = len(needle_tokens)
    if not needle_tokens or not hay_tokens:
        return False
    if n > 400:  # very long needles: strict containment only
        return False

    # Anchors: the first token plus the *rarest* long token (fewest matches).
    anchors = {needle_tokens[0]}
    long_tokens = [t for t in needle_tokens if len(t) >= 5]
    if long_tokens:
        anchors.add(min(long_tokens, key=lambda t: normalized_haystack.count(t)))

    max_occurrences = 200  # bound the work on pathological documents
    for anchor in anchors:
        if anchor not in needle_tokens:
            continue
        anchor_index = needle_tokens.index(anchor)
        occurrences = 0
        for i, token in enumerate(hay_tokens):
            if token != anchor:
                continue
            occurrences += 1
            if occurrences > max_occurrences:
                break
            begin = i - anchor_index
            if begin < 0:
                continue
            # Exact-length window, then windows tolerant of small insertions.
            windows = [hay_tokens[begin: begin + n]]
            for pad in (2, 5):
                windows.append(hay_tokens[begin: begin + n + pad])
                windows.append(hay_tokens[max(0, begin - pad): begin + n])
            for window in windows:
                if len(window) < max(2, n - max(2, n // 10)):
                    continue
                if SequenceMatcher(None, needle_tokens, window, autojunk=False).ratio() >= min_ratio:
                    return True
    return False


def quote_in_text(quote: str | None, text: str | None, min_ratio: float = QUOTE_MIN_RATIO) -> bool:
    """True when `quote` is present in `text` (normalized substring or fuzzy)."""
    if not quote or not text:
        return False
    nq, nt = normalize(quote), normalize(text)
    if not nq or not nt:
        return False
    if nq in nt:
        return True
    return _fuzzy_contains(nq, nt, min_ratio)


# --- date handling ---------------------------------------------------------

_DATE_FORMATS = (
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
    "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y",
    "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y",
    "%d.%m.%Y", "%Y%m%d",
)


def _parse_date(value: str) -> datetime | None:
    v = value.strip()
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def _datetime_in_text(value: str, normalized_text: str) -> bool:
    """Date/time equivalence check.

    The model may legitimately normalize "3-Oct-2026" to "2026-10-03". We accept
    that ONLY if the date actually appears in the document — and if the value
    carries a time component, the time must appear too (never accept an
    invented timestamp).
    """
    dt = _parse_date(value)
    if dt is None:
        return False
    date_forms = {dt.strftime(f) for f in _DATE_FORMATS} | {dt.date().isoformat()}
    date_found = any(normalize(f) in normalized_text for f in date_forms)
    if not date_found:
        return False
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        return True  # date-only value: nothing further to prove
    # A time was claimed: it must be present as HH:MM (optionally with :SS).
    hhmm = dt.strftime("%H:%M")
    hhmm_no_lead_zero = f"{dt.hour}:{dt.minute:02d}"
    return normalize(hhmm) in normalized_text or normalize(hhmm_no_lead_zero) in normalized_text


def value_in_text(value: str | None, text: str | None) -> bool:
    """True when an extracted value can be traced to the document.

    Checks, in order: normalized substring -> date/time equivalence ->
    fuzzy containment for multi-word values (>=4 words, ratio >= 0.85).
    Short non-matching values are rejected (safest behavior: never fabricate).
    """
    if not value or not text:
        return False
    nv, nt = normalize(value), normalize(text)
    if not nv or not nt:
        return False
    if nv in nt:
        return True
    if _datetime_in_text(value.strip(), nt):
        return True
    if len(nv.split()) >= 4:
        return _fuzzy_contains(nv, nt, VALUE_MIN_RATIO)
    return False
