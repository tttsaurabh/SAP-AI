"""
chunker.py — Semantic Chunking Engine
======================================
Implements token-aware semantic chunking that:
  - Chunks by token count (300–600 tokens), not character count
  - Preserves section boundaries (headings flush the current chunk)
  - Never splits atomic blocks:
      * ABAP / SQL / code fences (``` … ```)
      * SAP configuration tables (markdown | … | tables)
      * Numbered procedures (1. step … N. step)
      * Transaction code lists (T-Code blocks)
      * Diagrams with associated descriptions
  - Each chunk represents a complete concept
  - Overlap: 75–100 tokens (sentence-boundary-aware)
"""

import re
from typing import List, Dict, Any, Optional
from loguru import logger

# ──────────────────────────────────────────────────────────────────────────────
# Token counting — use tiktoken if available, else approximate at 4 chars/token
# ──────────────────────────────────────────────────────────────────────────────
try:
    import tiktoken
    _ENCODER = tiktoken.get_encoding("cl100k_base")

    def _token_len(text: str) -> int:
        return len(_ENCODER.encode(text))

except ImportError:
    _ENCODER = None

    def _token_len(text: str) -> int:
        """Approximate token count as chars / 4."""
        return max(1, len(text) // 4)


# ──────────────────────────────────────────────────────────────────────────────
# Atomic block detection helpers
# ──────────────────────────────────────────────────────────────────────────────

# Code fence starts (``` or ~~~), language-optional
_CODE_FENCE_RE = re.compile(r'^(`{3,}|~{3,})', re.MULTILINE)

# Markdown table row (| cell | cell |)
_TABLE_ROW_RE = re.compile(r'^\s*\|.+\|\s*$')

# Numbered procedure item  (1. step, 2. step …)
_NUMBERED_STEP_RE = re.compile(r'^\s*\d{1,2}\.\s+\S')

# T-Code / transaction-code list patterns
_TCODE_RE = re.compile(
    r'\b([A-Z]{2,4}\d{0,4})\b.*?(?:transaction|T-[Cc]ode|TCode)',
    re.IGNORECASE
)

# Heading patterns (Markdown #, or ALL-CAPS short lines, or numbered sections)
_HEADING_RE = re.compile(
    r'^(?:'
    r'#{1,6}\s+.{3,100}'                         # Markdown headings
    r'|CHAPTER\s+\d+\s*[:\-]\s*.{3,80}'          # CHAPTER X:
    r'|SECTION\s+\d+\s*[:\-]\s*.{3,80}'          # SECTION X:
    r'|\d+(\.\d+)*\s+[A-Z][A-Za-z ]{5,70}'       # 1.2.3 Title Case
    r')',
    re.IGNORECASE
)

_UPPER_HEADING_RE = re.compile(r'^(?=.*\s)[A-Z][A-Z0-9 :\/\-]{4,80}$')

# A run of this many or more consecutive heading-matching lines is treated as a
# Table of Contents / Index / glossary listing rather than real section headings
# (see _classify_segments). Verified empirically against public/*.pdf: on
# "SAP MDG ... Comprehensive Guide.pdf", 39 of 1234 pages (ToC/Index/glossary
# pages, one with 49 heading-pattern matches on a single page) accounted for
# 758 of 1132 total chunks before this fix, because each numbered listing line
# ("6.3.2   Simple Checks in...") matches the same regex as a real heading and
# individually flushes the chunk buffer.
_TOC_RUN_THRESHOLD = 3


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    return bool(_HEADING_RE.match(stripped)) or bool(_UPPER_HEADING_RE.match(stripped))


def _extract_heading_text(line: str) -> str:
    stripped = line.strip()
    # Strip leading # marks
    stripped = re.sub(r'^#+\s*', '', stripped)
    # Strip leading numbering like "1.2.3 "
    stripped = re.sub(r'^\d+(\.\d+)*\s+', '', stripped)
    return stripped.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Segment classifier — splits raw page text into semantic segments
# ──────────────────────────────────────────────────────────────────────────────

def _classify_segments(text: str) -> List[Dict[str, Any]]:
    """
    Split a page's text into typed segments:
      - type: "heading"    → section heading (flush trigger)
      - type: "code"       → fenced code block (atomic, never split)
      - type: "table"      → markdown table (atomic, never split)
      - type: "procedure"  → numbered procedure (atomic, never split)
      - type: "text"       → regular prose paragraph
    """
    segments: List[Dict[str, Any]] = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Fenced code block ───────────────────────────────────────────────
        if _CODE_FENCE_RE.match(line.strip()):
            fence_char = line.strip()[:3]
            block_lines = [line]
            i += 1
            while i < len(lines):
                block_lines.append(lines[i])
                if lines[i].strip().startswith(fence_char) and len(lines[i].strip()) >= 3 and i > len(block_lines) - 2:
                    i += 1
                    break
                i += 1
            segments.append({"type": "code", "text": "\n".join(block_lines)})
            continue

        # ── Markdown table ──────────────────────────────────────────────────
        if _TABLE_ROW_RE.match(line):
            block_lines = [line]
            i += 1
            while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
                block_lines.append(lines[i])
                i += 1
            segments.append({"type": "table", "text": "\n".join(block_lines)})
            continue

        # ── Numbered procedure ──────────────────────────────────────────────
        if _NUMBERED_STEP_RE.match(line):
            block_lines = [line]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if _NUMBERED_STEP_RE.match(nxt) or (nxt.startswith("   ") and nxt.strip()):
                    block_lines.append(nxt)
                    i += 1
                else:
                    break
            segments.append({"type": "procedure", "text": "\n".join(block_lines)})
            continue

        # ── Heading (or dense run of heading-like lines = ToC/Index listing) ──
        if _is_heading(line) and line.strip():
            # Look ahead for a run of consecutive heading-matching lines. A real
            # section heading in body prose is isolated (surrounded by
            # paragraph text); a dense back-to-back run of lines that each
            # individually match the heading regex is characteristic of a
            # Table of Contents, Index, or glossary listing, where treating
            # every line as its own heading would flush the chunk buffer once
            # per line and produce a near-empty chunk per entry.
            run_end = i
            while run_end < len(lines) and lines[run_end].strip() and _is_heading(lines[run_end]):
                run_end += 1
            run_length = run_end - i
            if run_length >= _TOC_RUN_THRESHOLD:
                block_lines = [lines[j].strip() for j in range(i, run_end)]
                segments.append({"type": "text", "text": "\n".join(block_lines)})
                i = run_end
                continue
            segments.append({"type": "heading", "text": line.strip()})
            i += 1
            continue

        # ── Blank line ───────────────────────────────────────────────────────
        if not line.strip():
            i += 1
            continue

        # ── Regular prose paragraph ──────────────────────────────────────────
        block_lines = [line]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            # Stop paragraph at blank line, heading, or atomic block start
            if (not nxt.strip()
                    or _is_heading(nxt)
                    or _CODE_FENCE_RE.match(nxt.strip())
                    or _TABLE_ROW_RE.match(nxt)
                    or _NUMBERED_STEP_RE.match(nxt)):
                break
            block_lines.append(nxt)
            i += 1
        segments.append({"type": "text", "text": "\n".join(block_lines).strip()})

    return [s for s in segments if s["text"].strip()]


# ──────────────────────────────────────────────────────────────────────────────
# Overlap helper — extract last N tokens from text (sentence-boundary aware)
# ──────────────────────────────────────────────────────────────────────────────

def _overlap_text(text: str, overlap_tokens: int) -> str:
    """Return the trailing <overlap_tokens>-token slice from text."""
    if not text.strip():
        return ""
    # Rough split by sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    result = ""
    for sent in reversed(sentences):
        candidate = sent + " " + result if result else sent
        if _token_len(candidate) <= overlap_tokens:
            result = candidate
        else:
            break
    return result.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Main Chunker
# ──────────────────────────────────────────────────────────────────────────────

class DocumentChunker:
    # Defaults tuned to user specification
    DEFAULT_CHUNK_SIZE_TOKENS: int = 450    # target size (300–600 token range)
    DEFAULT_CHUNK_OVERLAP_TOKENS: int = 80  # overlap (75–100 token range)

    @staticmethod
    def chunk_document(
        pages: List[Dict[str, Any]],
        chunk_size: int = DEFAULT_CHUNK_SIZE_TOKENS,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
    ) -> List[Dict[str, Any]]:
        """
        Semantic chunking pipeline.

        Parameters
        ----------
        pages : list of page dicts  { "page": int, "text": str, "metadata": dict }
        chunk_size : max tokens per chunk  (default 450)
        chunk_overlap : overlap tokens     (default 80)

        Returns
        -------
        List of chunk dicts compatible with downstream VectorDB / Pinecone upserts.
        """
        chunks: List[Dict[str, Any]] = []
        chunk_idx: int = 0
        current_header: str = "General Information"

        # Running buffer
        buffer_text: str = ""
        buffer_tokens: int = 0
        buffer_page: int = 1

        def _flush(text: str, page: int, header: str) -> None:
            nonlocal chunk_idx
            text = text.strip()
            if not text or _token_len(text) < 10:  # skip tiny fragments
                return
            chunks.append({
                "chunk_index": chunk_idx,
                "text": text,
                "page_number": page,
                "section_header": header,
                "chunk_metadata": {
                    "source_page": page,
                    "section": header,
                    "token_count": _token_len(text),
                }
            })
            chunk_idx += 1

        for p in pages:
            page_num = p.get("page", 1)
            page_text = p.get("text", "")
            page_metadata = p.get("metadata", {})

            # Update header from page-level metadata
            page_headings = page_metadata.get("headings", [])
            if page_headings:
                current_header = page_headings[0]

            if not page_text.strip():
                continue

            segments = _classify_segments(page_text)
            buffer_page = page_num

            for seg in segments:
                seg_type = seg["type"]
                seg_text = seg["text"]
                seg_tokens = _token_len(seg_text)

                # ── Heading → flush buffer, update header ──────────────────
                if seg_type == "heading":
                    if buffer_text:
                        _flush(buffer_text, buffer_page, current_header)
                        # Start new buffer with overlap
                        buffer_text = _overlap_text(buffer_text, chunk_overlap)
                        buffer_tokens = _token_len(buffer_text)
                    current_header = _extract_heading_text(seg_text)
                    continue

                # ── Atomic blocks (code, table, procedure) — never split ────
                if seg_type in ("code", "table", "procedure"):
                    if buffer_text:
                        # If atomic fits in remaining space, keep together
                        if buffer_tokens + seg_tokens <= chunk_size:
                            buffer_text += "\n\n" + seg_text
                            buffer_tokens += seg_tokens
                        else:
                            # Flush buffer first, then start new chunk with atomic
                            _flush(buffer_text, buffer_page, current_header)
                            overlap = _overlap_text(buffer_text, chunk_overlap)
                            buffer_text = (overlap + "\n\n" + seg_text).strip() if overlap else seg_text
                            buffer_tokens = _token_len(buffer_text)
                    else:
                        buffer_text = seg_text
                        buffer_tokens = seg_tokens
                    buffer_page = page_num

                    # If the atomic block itself exceeds chunk_size, flush it immediately
                    if buffer_tokens >= chunk_size:
                        _flush(buffer_text, buffer_page, current_header)
                        buffer_text = ""
                        buffer_tokens = 0
                    continue

                # ── Regular prose ──────────────────────────────────────────
                if buffer_tokens + seg_tokens <= chunk_size:
                    # Fits → append to buffer
                    buffer_text = (buffer_text + "\n\n" + seg_text).strip() if buffer_text else seg_text
                    buffer_tokens = _token_len(buffer_text)
                    buffer_page = page_num
                else:
                    # Doesn't fit → flush, start new buffer with overlap + segment
                    if buffer_text:
                        _flush(buffer_text, buffer_page, current_header)
                        overlap = _overlap_text(buffer_text, chunk_overlap)
                        buffer_text = (overlap + "\n\n" + seg_text).strip() if overlap else seg_text
                    else:
                        buffer_text = seg_text
                    buffer_tokens = _token_len(buffer_text)
                    buffer_page = page_num

                    # If a single segment is larger than chunk_size, hard-split it
                    while buffer_tokens > chunk_size:
                        # find split point at sentence boundary near chunk_size tokens
                        sentences = re.split(r'(?<=[.!?])\s+', buffer_text)
                        split_text = ""
                        remainder = buffer_text
                        for sent in sentences:
                            candidate = (split_text + " " + sent).strip() if split_text else sent
                            if _token_len(candidate) > chunk_size and split_text:
                                break
                            split_text = candidate
                            remainder = buffer_text[len(candidate):].strip()
                        if not split_text:
                            # Absolute fallback: just flush everything
                            split_text = buffer_text
                            remainder = ""
                        _flush(split_text, buffer_page, current_header)
                        overlap = _overlap_text(split_text, chunk_overlap)
                        buffer_text = (overlap + "\n\n" + remainder).strip() if (overlap and remainder) else remainder
                        buffer_tokens = _token_len(buffer_text) if buffer_text else 0

        # Flush remaining buffer
        if buffer_text:
            _flush(buffer_text, buffer_page, current_header)

        logger.info(
            f"Semantic chunking complete: {len(chunks)} chunks from {len(pages)} pages "
            f"(target {chunk_size} tokens, overlap {chunk_overlap} tokens)"
        )
        return chunks
