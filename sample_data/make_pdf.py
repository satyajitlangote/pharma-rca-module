"""Generate sample_data/yield_drop_incident.pdf from the .txt source.

Uses only the Python standard library (a minimal but valid PDF), so the sample
set can be regenerated offline:

    python sample_data/make_pdf.py

The PDF exists so the "Upload PDF" tab can be tested with a realistic file;
/api/samples extracts its text with pypdf at request time.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "yield_drop_incident.txt"
TARGET = HERE / "yield_drop_incident.pdf"

LINE_WIDTH = 92  # characters per line for 10pt Helvetica in a 512pt column


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(line: str, width: int = LINE_WIDTH) -> list[str]:
    if len(line) <= width:
        return [line]
    words, out, current = line.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            out.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        out.append(current)
    return out


def build_pdf(text: str) -> bytes:
    lines: list[str] = []
    for raw in text.splitlines():
        lines.extend(_wrap(raw) if raw.strip() else [""])

    # Page 1..n of 46 lines each
    pages = [lines[i : i + 46] for i in range(0, len(lines), 46)] or [[]]

    content_streams = []
    for page in pages:
        parts = ["BT", "/F1 9.5 Tf", "13 TL", "50 770 Td"]
        for line in page:
            parts.append(f"({_escape(line)}) Tj T*")
        parts.append("ET")
        content_streams.append("\n".join(parts).encode("latin-1", errors="replace"))

    objects: list[bytes] = []
    n_pages = len(pages)
    # 1 Catalog, 2 Pages, then per page: Page obj + Contents obj, last: Font
    page_ids = [3 + 2 * i for i in range(n_pages)]
    content_ids = [4 + 2 * i for i in range(n_pages)]
    font_id = 3 + 2 * n_pages

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")                                  # 1
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())         # 2
    for i, (pid, cid) in enumerate(zip(page_ids, content_ids)):
        assert pid == 3 + 2 * i
        objects.append(                                                # page
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {cid} 0 R >>".encode()
        )
        stream = content_streams[i]
        objects.append(                                                # contents
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")             # font

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


def main() -> None:
    pdf = build_pdf(SOURCE.read_text(encoding="utf-8"))
    TARGET.write_bytes(pdf)

    # Self-check with pypdf (same extractor the API uses).
    from pypdf import PdfReader

    extracted = "\n".join((p.extract_text() or "") for p in PdfReader(TARGET).pages)
    assert "IBU-26-0033" in extracted, "PDF text extraction failed"
    print(f"wrote {TARGET} ({len(pdf):,} bytes, {len(extracted):,} chars extracted)")


if __name__ == "__main__":
    main()
