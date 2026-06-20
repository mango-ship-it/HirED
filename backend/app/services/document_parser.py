"""Resume document parsing: raw bytes (PDF / DOCX / plain text) -> clean text.

Per API_CONTRACT.md the frontend uploads the raw file and the backend parses it.
This module turns the uploaded bytes into normalized plain text; that text is then
handed to Claude (`claude_service.extract_profile`) to produce the structured,
tool-usable JSON profile. So the pipeline is:

    upload (PDF/DOCX/text)  ->  extract_text()  ->  plain text  ->  Claude  ->  JSON profile

Pure and dependency-light: no network, no global state. PDF uses pdfplumber
(layout-aware, good for multi-column resume PDFs) with a pypdf fallback; DOCX uses
python-docx. Anything unreadable raises a typed error the route maps to a clean
contract error response — never a 500 stack trace.
"""

from __future__ import annotations

import io
import re

# Accepted inputs.
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT_MIMES = frozenset({"text/plain", "text/markdown", "application/octet-stream"})
RTF_MIMES = frozenset({"application/rtf", "text/rtf"})

# Reject oversized uploads before doing any work (matches the route's guardrail).
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB

# Magic bytes for content sniffing when the client sends a generic content-type.
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"  # DOCX is a zip container
_RTF_MAGIC = b"{\\rtf"


class UnsupportedDocumentError(ValueError):
    """The document is not a PDF, DOCX, or plain text we can parse."""


class DocumentParseError(ValueError):
    """The document is a supported type but yielded no usable text."""


def _detect_kind(content_type: str | None, filename: str | None, data: bytes) -> str:
    """Decide pdf | docx | text from filename, then content-type, then magic bytes."""
    name = (filename or "").strip().lower()
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".docx"):
        return "docx"
    if name.endswith(".rtf"):
        return "rtf"
    if name.endswith((".txt", ".md", ".text")):
        return "text"

    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime == PDF_MIME:
        return "pdf"
    if mime == DOCX_MIME:
        return "docx"
    if mime in RTF_MIMES:
        return "rtf"

    # Fall back to sniffing the bytes (generic octet-stream uploads land here).
    if data.startswith(_PDF_MAGIC):
        return "pdf"
    if data.startswith(_RTF_MAGIC):
        return "rtf"
    if data.startswith(_ZIP_MAGIC):
        return "docx"
    if mime in TEXT_MIMES:
        return "text"

    raise UnsupportedDocumentError(
        f"Unsupported document (content_type={content_type!r}, filename={filename!r}). "
        "Accepted: PDF, DOCX, or plain text."
    )


def _normalize(text: str) -> str:
    """Collapse runaway whitespace while keeping paragraph breaks readable."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def _extract_pdf(data: bytes) -> str:
    """Extract text from PDF bytes: pdfplumber first, pypdf as a fallback."""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(pages)
        if text.strip():
            return text
    except DocumentParseError:
        raise
    except Exception:
        text = ""  # fall through to pypdf

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise DocumentParseError(f"Could not read PDF: {exc}") from exc


def _extract_docx(data: bytes) -> str:
    """Extract text from DOCX bytes (paragraphs + table cells)."""
    try:
        from docx import Document

        document = Document(io.BytesIO(data))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
        return "\n".join(parts)
    except Exception as exc:
        raise DocumentParseError(f"Could not read DOCX: {exc}") from exc


def _extract_rtf(data: bytes) -> str:
    """Extract plain text from RTF bytes (strips RTF control words)."""
    try:
        from striprtf.striprtf import rtf_to_text

        return rtf_to_text(data.decode("utf-8", errors="replace"))
    except Exception as exc:
        raise DocumentParseError(f"Could not read RTF: {exc}") from exc


def extract_text(
    data: bytes,
    *,
    content_type: str | None = None,
    filename: str | None = None,
) -> str:
    """Parse uploaded document bytes into normalized plain text.

    Raises:
        UnsupportedDocumentError: the type is not PDF/DOCX/text.
        DocumentParseError: empty, too large, or no extractable text
            (e.g. a scanned/image-only PDF — we do not OCR).
    """
    if not data:
        raise DocumentParseError("Empty document upload.")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentParseError(
            f"Document too large ({len(data)} bytes; max {MAX_DOCUMENT_BYTES})."
        )

    kind = _detect_kind(content_type, filename, data)
    if kind == "text":
        raw = data.decode("utf-8", errors="replace")
    elif kind == "rtf":
        raw = _extract_rtf(data)
    elif kind == "docx":
        raw = _extract_docx(data)
    else:
        raw = _extract_pdf(data)

    text = _normalize(raw)
    if not text:
        raise DocumentParseError(
            "No extractable text found. If this is a scanned/image PDF, paste the "
            "resume text instead (we do not OCR images)."
        )
    return text
