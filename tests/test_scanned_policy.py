import pymupdf
import pytest

from app.ingestion.pymupdf_parser import (
    PyMuPDFParser,
    ScannedPDFError,
)


def create_textless_pdf(path, pages: int = 2) -> None:
    """A PDF with pages but no text layer — what a scan looks like."""

    document = pymupdf.open()

    for _ in range(pages):
        document.new_page()

    document.save(path)
    document.close()


def create_mixed_pdf(path, text_pages: int, blank_pages: int) -> None:

    document = pymupdf.open()

    for index in range(text_pages):
        page = document.new_page()

        page.insert_text(
            (72, 72),
            f"Page {index} of a paper with a real text layer.",
        )

    for _ in range(blank_pages):
        document.new_page()

    document.save(path)
    document.close()


def test_a_textless_pdf_is_rejected(tmp_path):

    path = tmp_path / "scanned.pdf"

    create_textless_pdf(path)

    with pytest.raises(ScannedPDFError) as error:
        PyMuPDFParser().parse(path)

    message = str(error.value)

    assert "scanned.pdf" in message
    assert "OCR" in message


def test_a_mostly_textless_pdf_is_rejected(tmp_path):

    path = tmp_path / "mostly_scanned.pdf"

    create_mixed_pdf(path, text_pages=1, blank_pages=4)

    with pytest.raises(ScannedPDFError):
        PyMuPDFParser().parse(path)


def test_allow_scanned_downgrades_rejection_to_a_warning(tmp_path):

    path = tmp_path / "scanned.pdf"

    create_textless_pdf(path)

    paper = PyMuPDFParser(allow_scanned=True).parse(path)

    assert paper.page_count == 2
    assert any("accepted anyway" in warning for warning in paper.warnings)


def test_a_pdf_with_a_real_text_layer_is_not_rejected(tmp_path):

    path = tmp_path / "normal.pdf"

    create_mixed_pdf(path, text_pages=4, blank_pages=1)

    paper = PyMuPDFParser().parse(path)

    assert paper.page_count == 5
    assert paper.full_text.strip()

    # The one blank page still earns a warning rather than passing silently.
    assert any("no extractable text" in warning for warning in paper.warnings)
