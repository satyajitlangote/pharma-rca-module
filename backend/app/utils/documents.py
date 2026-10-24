"""Document intake: PDF / .eml email / plain text -> plain text.

Rules:
  * Never invent content. A scanned PDF is an explicit, actionable error.
  * Email headers (From/Subject/Date) are part of the returned text so that
    extraction quotes taken from headers can still be verified against it.
  * Long text is truncated with a visible warning (flag returned to the UI).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from email import policy
from email.message import Message
from email.parser import BytesParser, Parser


class DocumentError(Exception):
    """User-facing input problem (mapped to HTTP 4xx with a clear message)."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ParsedDocument:
    text: str
    filename: str | None = None
    kind: str = "text"                      # "pdf" | "email" | "text"
    email_headers: dict = field(default_factory=dict)
    truncated: bool = False
    warning: str | None = None


def _truncate(text: str, max_chars: int) -> tuple[str, bool, str | None]:
    if len(text) <= max_chars:
        return text, False, None
    cut = text[:max_chars]
    warning = (
        f"Document truncated to {max_chars:,} of {len(text):,} characters — "
        "information after that point was not analyzed."
    )
    return cut, True, warning


# --- PDF -------------------------------------------------------------------

def parse_pdf(data: bytes, filename: str | None, max_chars: int) -> ParsedDocument:
    from pypdf import PdfReader  # imported here: keeps startup light

    if not data:
        raise DocumentError("The uploaded PDF is empty.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # Some PDFs have an empty user password; try that, otherwise fail.
            if not reader.decrypt(""):
                raise DocumentError(
                    "The PDF is encrypted/password-protected — remove the "
                    "password or paste the text instead."
                )
        pages = [(page.extract_text() or "") for page in reader.pages]
    except DocumentError:
        raise
    except Exception as exc:  # corrupt file
        raise DocumentError(f"Could not read the PDF file: {exc}") from exc

    text = "\n\n".join(p for p in pages).strip()
    if not text:
        raise DocumentError(
            "No extractable text found in this PDF. Scanned/image-only PDFs are "
            "not supported — please paste the document text (or email) instead.",
            status_code=422,
        )
    text, truncated, warning = _truncate(text, max_chars)
    return ParsedDocument(text=text, filename=filename, kind="pdf",
                          truncated=truncated, warning=warning)


# --- email -----------------------------------------------------------------

_HEADER_NAMES = ("From", "To", "Subject", "Date", "Cc")


def _headers_of(msg: Message) -> dict:
    return {h: str(msg[h]).strip() for h in _HEADER_NAMES if msg.get(h)}


def _body_of(msg: Message) -> str:
    if msg.is_multipart():
        part = msg.get_body(preferencelist=("plain",))
        if part is None:
            for p in msg.walk():
                if p.get_content_type() == "text/plain":
                    part = p
                    break
        if part is not None:
            try:
                return part.get_content()
            except Exception:
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return str(msg.get_payload() or "")


def _assemble(headers: dict, body: str) -> str:
    lines = [f"{name}: {value}" for name, value in headers.items()]
    return ("\n".join(lines) + "\n\n" + body.strip()).strip()


def parse_email_bytes(data: bytes, filename: str | None, max_chars: int) -> ParsedDocument:
    msg = BytesParser(policy=policy.default).parsebytes(data)
    headers, body = _headers_of(msg), _body_of(msg)
    if not headers and not body.strip():
        raise DocumentError("The .eml file appears to be empty or unreadable.")
    text, truncated, warning = _truncate(_assemble(headers, body), max_chars)
    return ParsedDocument(text=text, filename=filename, kind="email",
                          email_headers=headers, truncated=truncated, warning=warning)


def looks_like_email(text: str) -> bool:
    """True when the pasted text starts with RFC822-style headers."""
    head = "\n".join(text.splitlines()[:15]).lower()
    has_from = re.search(r"^from:\s*\S+", head, re.MULTILINE) is not None
    has_subject = re.search(r"^subject:\s*.+", head, re.MULTILINE) is not None
    return has_from and (has_subject or re.search(r"^date:\s*.+", head, re.MULTILINE) is not None)


def parse_email_text(text: str, max_chars: int) -> ParsedDocument:
    """Pasted email: keep the ORIGINAL text (so quotes verify against it),
    but pull out headers for context (reported_by, incident date)."""
    msg = Parser(policy=policy.default).parsestr(text)
    headers = _headers_of(msg)
    kept, truncated, warning = _truncate(text, max_chars)
    return ParsedDocument(text=kept, kind="email", email_headers=headers,
                          truncated=truncated, warning=warning)


# --- dispatch --------------------------------------------------------------

def parse_upload(data: bytes, filename: str | None, content_type: str | None,
                 max_chars: int) -> ParsedDocument:
    """Pick the parser from the file name / content type / magic bytes."""
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    if data[:5] == b"%PDF-" or name.endswith(".pdf") or "pdf" in ct:
        return parse_pdf(data, filename, max_chars)
    if name.endswith(".eml") or name.endswith(".msg") or "message/rfc822" in ct:
        return parse_email_bytes(data, filename, max_chars)
    # Unknown extension: try text decode, then email headers.
    text = data.decode("utf-8", errors="replace")
    if looks_like_email(text):
        return parse_email_text(text, max_chars)
    return parse_text(text, filename, max_chars)


def parse_text(text: str, filename: str | None, max_chars: int) -> ParsedDocument:
    if looks_like_email(text):
        doc = parse_email_text(text, max_chars)
        doc.filename = filename
        return doc
    kept, truncated, warning = _truncate(text, max_chars)
    return ParsedDocument(text=kept, filename=filename, kind="text",
                          truncated=truncated, warning=warning)
