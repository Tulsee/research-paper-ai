import pymupdf

from app.chunking.section_chunker import (
    SectionChunker,
)

from app.extraction.enrich_paper import (
    enrich_paper,
)

from app.ingestion.pymupdf_parser import (
    PyMuPDFParser,
)


def create_long_pdf(path):

    document = pymupdf.open()

    page = document.new_page()

    page.insert_text(
        (70, 70),
        "A Machine Learning Study",
        fontsize=20,
        fontname="hebo",
    )

    page.insert_text(
        (70, 120),
        "1 Introduction",
        fontsize=14,
        fontname="hebo",
    )

    y = 150

    for i in range(120):

        page.insert_text(
            (70, y),
            (
                f"Introduction sentence {i}. "
                "Machine learning provides useful "
                "methods for analyzing complex datasets."
            ),
            fontsize=8,
        )

        y += 12

        if y > 750:
            page = document.new_page()
            y = 50

    page = document.new_page()

    page.insert_text(
        (70, 70),
        "2 Methodology",
        fontsize=14,
        fontname="hebo",
    )

    y = 100

    for i in range(120):

        page.insert_text(
            (70, y),
            (
                f"Methodology sentence {i}. "
                "The proposed method evaluates "
                "multiple machine learning models."
            ),
            fontsize=8,
        )

        y += 12

        if y > 750:
            page = document.new_page()
            y = 50

    document.save(path)
    document.close()


def load_paper(path):

    paper = PyMuPDFParser().parse(path)

    paper = enrich_paper(paper)

    paper = SectionChunker(
        target_tokens=100,
        overlap_ratio=0.15,
    ).chunk_paper(paper)

    return paper


def test_chunks_are_created(tmp_path):

    path = tmp_path / "long.pdf"

    create_long_pdf(path)

    paper = load_paper(path)

    assert len(paper.chunks) > 0


def test_chunks_have_token_limits(tmp_path):

    path = tmp_path / "long.pdf"

    create_long_pdf(path)

    paper = load_paper(path)

    for chunk in paper.chunks:

        assert chunk.token_count <= 100


def test_chunks_have_section_metadata(tmp_path):

    path = tmp_path / "long.pdf"

    create_long_pdf(path)

    paper = load_paper(path)

    for chunk in paper.chunks:

        assert chunk.section_id
        assert chunk.section_heading
        assert chunk.page_start >= 1
        assert chunk.page_end >= chunk.page_start


def test_chunk_offsets_are_valid(tmp_path):

    path = tmp_path / "long.pdf"

    create_long_pdf(path)

    paper = load_paper(path)

    for chunk in paper.chunks:

        extracted = paper.full_text[chunk.start_char : chunk.end_char]

        assert extracted.strip() == chunk.text.strip()


def test_chunks_do_not_cross_sections(tmp_path):

    path = tmp_path / "long.pdf"

    create_long_pdf(path)

    paper = load_paper(path)

    for chunk in paper.chunks:

        section = next(
            section
            for section in paper.sections
            if section.section_id == chunk.section_id
        )

        assert chunk.start_char >= section.start_char

        assert chunk.end_char <= section.end_char
