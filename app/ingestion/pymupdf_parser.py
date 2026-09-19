from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf

from app.models.paper import Paper, PaperPage, TextBlock


class PDFIngestionError(Exception):
    """Raised when a PDF cannot be ingested successfully."""


class PyMuPDFParser:
    """Extract normalized, page-aware text from a PDF."""

    parser_name = "pymupdf"
    parser_version = pymupdf.VersionBind

    def parse(self, pdf_path: str | Path) -> Paper:
        path = Path(pdf_path)

        if not path.exists():
            raise PDFIngestionError(f"PDF file does not exist: {path}")

        if not path.is_file():
            raise PDFIngestionError(f"Path is not a file: {path}")

        if path.suffix.lower() != ".pdf":
            raise PDFIngestionError(f"Expected a PDF file, received: {path.suffix}")

        paper_id = self._calculate_paper_id(path)

        try:
            document = pymupdf.open(path)
        except Exception as exc:
            raise PDFIngestionError(f"Could not open PDF '{path}': {exc}") from exc

        if document.is_encrypted:
            if not document.authenticate(""):
                document.close()
                raise PDFIngestionError(
                    "The PDF is password-protected and could not be opened."
                )

        if document.page_count == 0:
            document.close()
            raise PDFIngestionError("The PDF contains no pages.")

        pages: list[PaperPage] = []
        all_text_parts: list[str] = []
        warnings: list[str] = []

        # Tracks the position of the next text block in full_text.
        current_offset = 0

        try:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)

                page_number = page_index + 1
                page_width = float(page.rect.width)
                page_height = float(page.rect.height)

                raw_blocks = page.get_text(
                    "blocks",
                    sort=True,
                )

                page_blocks: list[TextBlock] = []
                page_text_parts: list[str] = []

                for block_index, raw_block in enumerate(raw_blocks):
                    # A standard text block has at least:
                    # x0, y0, x1, y1, text, block_no, block_type
                    if len(raw_block) < 7:
                        warnings.append(
                            f"Page {page_number}: " f"malformed block {block_index}."
                        )
                        continue

                    x0, y0, x1, y1, text, _, block_type = raw_block[:7]

                    if not isinstance(text, str):
                        warnings.append(
                            f"Page {page_number}: "
                            f"block {block_index} has invalid text."
                        )
                        continue

                    # Ignore empty blocks, but preserve a warning for
                    # non-text blocks that may represent images.
                    cleaned_text = text.strip()

                    if not cleaned_text:
                        continue

                    block_id = f"{paper_id}:page-{page_number}:" f"block-{block_index}"

                    # Add a separator between blocks so that text from
                    # adjacent blocks does not run together.
                    if all_text_parts:
                        all_text_parts.append("\n\n")
                        current_offset += 2

                    start_char = current_offset
                    all_text_parts.append(cleaned_text)
                    current_offset += len(cleaned_text)
                    end_char = current_offset

                    page_text_parts.append(cleaned_text)

                    page_blocks.append(
                        TextBlock(
                            block_id=block_id,
                            page_number=page_number,
                            start_char=start_char,
                            end_char=end_char,
                            text=cleaned_text,
                            bbox=(
                                float(x0),
                                float(y0),
                                float(x1),
                                float(y1),
                            ),
                            block_index=block_index,
                            block_type=int(block_type),
                        )
                    )

                page_text = "\n\n".join(page_text_parts)

                if not page_text.strip():
                    warnings.append(
                        f"Page {page_number}: no extractable text found. "
                        "The page may be scanned, image-only, or empty."
                    )

                pages.append(
                    PaperPage(
                        page_number=page_number,
                        width=page_width,
                        height=page_height,
                        blocks=page_blocks,
                        text=page_text,
                    )
                )

        finally:
            document.close()

        full_text = "".join(all_text_parts)

        if len(full_text.strip()) < 100:
            warnings.append(
                "The document contains very little extractable text. "
                "It may be scanned, image-only, or poorly encoded."
            )

        return Paper(
            paper_id=paper_id,
            source_path=str(path.resolve()),
            filename=path.name,
            full_text=full_text,
            pages=pages,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            warnings=warnings,
            page_count=len(pages),
            extracted_char_count=len(full_text),
        )

    @staticmethod
    def _calculate_paper_id(path: Path) -> str:
        """Generate a deterministic ID from the PDF's contents."""

        digest = hashlib.sha256()

        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)

        return digest.hexdigest()[:16]
