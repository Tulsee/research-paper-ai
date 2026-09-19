from pathlib import Path

import pymupdf

from app.ingestion.pymupdf_parser import PyMuPDFParser


def create_test_pdf(path: Path) -> None:
    """Create a small two-page PDF for testing."""

    document = pymupdf.open()

    page_one = document.new_page()
    page_one.insert_text(
        (72, 72),
        "Research Paper Test\nIntroduction\n" "This is the first page of the paper.",
    )

    page_two = document.new_page()
    page_two.insert_text(
        (72, 72),
        "Methods\n" "This is the second page of the paper.",
    )

    document.save(path)
    document.close()


def test_parse_pdf_preserves_page_and_character_offsets(tmp_path):
    pdf_path = tmp_path / "test_paper.pdf"
    create_test_pdf(pdf_path)

    parser = PyMuPDFParser()
    paper = parser.parse(pdf_path)

    assert paper.page_count == 2
    assert len(paper.pages) == 2
    assert paper.full_text
    assert paper.extracted_char_count == len(paper.full_text)

    all_blocks = [block for page in paper.pages for block in page.blocks]

    assert all_blocks

    for block in all_blocks:
        extracted = paper.full_text[block.start_char : block.end_char]

        assert extracted == block.text
        assert block.page_number >= 1
        assert block.end_char > block.start_char
        assert block.block_id.startswith(paper.paper_id)


def test_paper_id_is_deterministic(tmp_path):
    pdf_path = tmp_path / "test_paper.pdf"
    create_test_pdf(pdf_path)

    parser = PyMuPDFParser()

    first = parser.parse(pdf_path)
    second = parser.parse(pdf_path)

    assert first.paper_id == second.paper_id
