from __future__ import annotations

import hashlib
from pathlib import Path

import fitz

from app.models.paper import Paper, PaperPage, TextBlock


class PDFIngestionError(Exception):
    """Raised when a PDF cannot be ingested."""


class PyMuPDFParser:
    parser_name = "pymupdf"

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
            document = fitz.open(path)
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

                for raw_block in page_dict.get("blocks", []):
                    # 0 = text block
                    # 1 = image block
                    block_type = int(raw_block.get("type", 0))

                    if block_type != 0:
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
                    warnings.append(f"Page {page_number}: no extractable text.")

                pages.append(
                    PaperPage(
                        page_number=page_number,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        blocks=page_blocks,
                        text=page_text,
                    )
                )

            full_text = "".join(all_text_parts)

            if len(full_text.strip()) < 100:
                warnings.append(
                    "Very little text was extracted. "
                    "The PDF may be scanned/image-only."
                )

            return Paper(
                schema_version="1.0",
                paper_id=paper_id,
                source_path=str(path.resolve()),
                filename=path.name,
                full_text=full_text,
                pages=pages,
                warnings=warnings,
                parser=self.parser_name,
                parser_version=fitz.version[0],
                page_count=len(pages),
                extracted_char_count=len(full_text),
            )

        finally:
            document.close()
