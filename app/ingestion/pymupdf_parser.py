from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf

from app.models.paper import Paper, PaperPage, TextBlock


def _summarize_pages(page_numbers: list[int], limit: int = 10) -> str:
    """Render a page list for error messages, e.g. "1, 2, 3 and 4 more"."""

    shown = ", ".join(str(number) for number in page_numbers[:limit])

    remaining = len(page_numbers) - limit

    if remaining > 0:
        return f"{shown} and {remaining} more"

    return shown


class PDFIngestionError(Exception):
    """Raised when a PDF cannot be ingested."""


class ScannedPDFError(PDFIngestionError):
    """Raised when a PDF has no usable text layer and would need OCR."""


class PyMuPDFParser:
    parser_name = "pymupdf"

    def __init__(
        self,
        allow_scanned: bool = False,
        max_empty_page_ratio: float = 0.5,
    ):
        """
        v1 policy: scanned PDFs are rejected, not OCR'd.

        A paper whose text layer is missing or mostly missing would flow
        downstream as a silently thin ``Paper`` and corrupt every later
        stage, so it fails loudly here instead. ``allow_scanned=True``
        downgrades the rejection to a warning for deliberate inspection
        of a known-bad PDF.
        """

        self.allow_scanned = allow_scanned

        self.max_empty_page_ratio = max_empty_page_ratio

    def _generate_paper_id(self, path: Path) -> str:
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        return file_hash[:16]

    def _extract_block_font_info(
        self,
        block: dict,
    ) -> tuple[float | None, str | None, bool]:
        """
        Extract representative font information from a PDF text block.

        A block can contain multiple lines/spans, so we use:
        - maximum font size
        - first available font name
        - bold=True if any span is bold
        """

        sizes: list[float] = []
        fonts: list[str] = []
        is_bold = False

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("size") is not None:
                    sizes.append(float(span["size"]))

                if span.get("font"):
                    fonts.append(str(span["font"]))

                font_name = str(span.get("font", "")).lower()

                # Common PDF font naming conventions
                flags = int(span.get("flags", 0))

                if (
                    "bold" in font_name
                    or "black" in font_name
                    or "heavy" in font_name
                    or flags & 16
                ):
                    is_bold = True

        font_size = max(sizes) if sizes else None
        font_name = fonts[0] if fonts else None

        return font_size, font_name, is_bold

    def _apply_scanned_policy(
        self,
        path: Path,
        pages: list[PaperPage],
        full_text: str,
        warnings: list[str],
    ) -> None:
        """Reject a PDF with no usable text layer (see ``__init__``)."""

        empty_pages = [page.page_number for page in pages if not page.blocks]

        empty_ratio = len(empty_pages) / len(pages) if pages else 1.0

        if not full_text.strip():
            reason = (
                f"No text could be extracted from any of the {len(pages)} page(s)."
            )

        elif empty_ratio > self.max_empty_page_ratio:
            reason = (
                f"{len(empty_pages)} of {len(pages)} pages have no extractable "
                f"text (pages {_summarize_pages(empty_pages)})."
            )

        else:
            return

        if self.allow_scanned:
            warnings.append(f"Scanned/image-only PDF accepted anyway: {reason}")
            return

        raise ScannedPDFError(
            f"{path.name} appears to be scanned or image-only. {reason} "
            "This PDF needs OCR before it can be ingested; v1 does not OCR. "
            "Pass allow_scanned=True to ingest it anyway, accepting that the "
            "resulting Paper will be incomplete."
        )

    def parse(self, pdf_path: str | Path) -> Paper:
        path = Path(pdf_path)

        if not path.exists():
            raise PDFIngestionError(f"PDF does not exist: {path}")

        if not path.is_file():
            raise PDFIngestionError(f"Path is not a file: {path}")

        if path.suffix.lower() != ".pdf":
            raise PDFIngestionError(f"Expected a PDF file: {path}")

        paper_id = self._generate_paper_id(path)

        warnings: list[str] = []
        pages: list[PaperPage] = []

        all_text_parts: list[str] = []
        current_char_offset = 0

        try:
            document = pymupdf.open(path)
        except Exception as exc:
            raise PDFIngestionError(f"Could not open PDF: {exc}") from exc

        try:
            if document.needs_pass:
                if not document.authenticate(""):
                    raise PDFIngestionError(
                        "PDF is password protected and could not be opened."
                    )

            if document.page_count == 0:
                raise PDFIngestionError("PDF contains no pages.")

            pdf_metadata = {
                key: value
                for key, value in (document.metadata or {}).items()
                if isinstance(value, str) and value.strip()
            }

            for page_index in range(document.page_count):
                page = document.load_page(page_index)

                page_number = page_index + 1

                page_blocks: list[TextBlock] = []
                page_text_parts: list[str] = []

                # dict extraction preserves font/layout information
                page_dict = page.get_text(
                    "dict",
                    sort=True,
                )

                text_block_index = 0
                image_block_count = 0

                for raw_block in page_dict.get("blocks", []):
                    # 0 = text block
                    # 1 = image block
                    block_type = int(raw_block.get("type", 0))

                    if block_type != 0:
                        image_block_count += 1
                        continue

                    lines = raw_block.get("lines", [])

                    line_texts: list[str] = []

                    for line in lines:
                        spans = line.get("spans", [])

                        span_text = "".join(str(span.get("text", "")) for span in spans)

                        if span_text.strip():
                            line_texts.append(span_text)

                    text = "\n".join(line_texts).strip()

                    if not text:
                        continue

                    bbox = raw_block.get(
                        "bbox",
                        (0.0, 0.0, 0.0, 0.0),
                    )

                    font_size, font_name, is_bold = self._extract_block_font_info(
                        raw_block
                    )

                    # Keep offsets deterministic.
                    if all_text_parts:
                        separator = "\n\n"
                        all_text_parts.append(separator)
                        current_char_offset += len(separator)

                    start_char = current_char_offset

                    all_text_parts.append(text)

                    current_char_offset += len(text)

                    end_char = current_char_offset

                    block_id = f"{paper_id}:p{page_number}:b{text_block_index}"

                    text_block = TextBlock(
                        block_id=block_id,
                        page_number=page_number,
                        start_char=start_char,
                        end_char=end_char,
                        text=text,
                        bbox=(
                            float(bbox[0]),
                            float(bbox[1]),
                            float(bbox[2]),
                            float(bbox[3]),
                        ),
                        block_index=text_block_index,
                        block_type=block_type,
                        font_size=font_size,
                        font_name=font_name,
                        is_bold=is_bold,
                    )

                    page_blocks.append(text_block)
                    page_text_parts.append(text)

                    text_block_index += 1

                page_text = "\n\n".join(page_text_parts)

                if not page_blocks:
                    if image_block_count:
                        warnings.append(
                            f"Page {page_number}: no extractable text "
                            f"({image_block_count} image(s) only). "
                            "This page is likely scanned and would need OCR."
                        )
                    else:
                        warnings.append(f"Page {page_number}: no extractable text.")

                pages.append(
                    PaperPage(
                        page_number=page_number,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        blocks=page_blocks,
                        text=page_text,
                        image_count=image_block_count,
                    )
                )

            full_text = "".join(all_text_parts)

            if len(full_text.strip()) < 100:
                warnings.append(
                    "Very little text was extracted. "
                    "The PDF may be scanned/image-only."
                )

            self._apply_scanned_policy(
                path=path,
                pages=pages,
                full_text=full_text,
                warnings=warnings,
            )

            return Paper(
                schema_version="1.0",
                paper_id=paper_id,
                source_path=str(path.resolve()),
                filename=path.name,
                full_text=full_text,
                pages=pages,
                warnings=warnings,
                pdf_metadata=pdf_metadata,
                parser=self.parser_name,
                parser_version=pymupdf.version[0],
                page_count=len(pages),
                extracted_char_count=len(full_text),
            )

        finally:
            document.close()
