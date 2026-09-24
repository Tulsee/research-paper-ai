import pymupdf

from app.extraction.enrich_paper import enrich_paper
from app.ingestion.pymupdf_parser import PyMuPDFParser


def create_pdf_with_image_cover(path, metadata_title=None):
    """
    A PDF whose first page carries no text at all, like the designed
    cover pages produced by thesis templates.
    """

    document = pymupdf.open()

    cover = document.new_page()

    cover.draw_rect(
        cover.rect,
        color=(0.2, 0.3, 0.8),
        fill=(0.2, 0.3, 0.8),
    )

    page = document.new_page()

    page.insert_text(
        (70, 80),
        "Introduction",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 110),
        "Deep learning is widely used to study neurodegenerative disease.",
        fontsize=10,
    )

    if metadata_title:
        document.set_metadata({"title": metadata_title})

    document.save(path)
    document.close()


def create_pdf_with_uncaptioned_table(path):
    document = pymupdf.open()

    page = document.new_page()

    page.insert_text(
        (70, 60),
        "A Study Of Grids",
        fontsize=20,
        fontname="hebo",
    )

    columns = [70, 200, 330, 460]
    rows = [100, 130, 160, 190]

    for y in rows:
        page.draw_line((columns[0], y), (columns[-1], y))

    for x in columns:
        page.draw_line((x, rows[0]), (x, rows[-1]))

    cells = [
        ["Model", "Accuracy", "F1"],
        ["Baseline", "0.71", "0.68"],
        ["Proposed", "0.88", "0.86"],
    ]

    for row_index, row in enumerate(cells):
        for column_index, value in enumerate(row):
            page.insert_text(
                (columns[column_index] + 5, rows[row_index] + 20),
                value,
                fontsize=9,
            )

    document.save(path)
    document.close()


def test_title_comes_from_metadata_when_cover_is_an_image(tmp_path):
    pdf_path = tmp_path / "cover.pdf"

    create_pdf_with_image_cover(
        pdf_path,
        metadata_title="A Multimodal Framework For Early Detection",
    )

    paper = enrich_paper(PyMuPDFParser().parse(pdf_path))

    assert paper.title == "A Multimodal Framework For Early Detection"


def test_no_title_is_invented_from_body_text(tmp_path):
    pdf_path = tmp_path / "cover_no_metadata.pdf"

    create_pdf_with_image_cover(pdf_path)

    paper = enrich_paper(PyMuPDFParser().parse(pdf_path))

    # The title only exists inside the cover image, so it must not be
    # guessed from a heading or a sentence of body text.
    assert paper.title is None

    assert any("OCR" in warning for warning in paper.warnings)


def test_filename_like_metadata_title_is_ignored(tmp_path):
    pdf_path = tmp_path / "word.pdf"

    create_pdf_with_image_cover(
        pdf_path,
        metadata_title="Microsoft Word - thesis final v3.docx",
    )

    paper = enrich_paper(PyMuPDFParser().parse(pdf_path))

    assert paper.title is None


def test_uncaptioned_table_is_detected_from_layout(tmp_path):
    pdf_path = tmp_path / "grid.pdf"

    create_pdf_with_uncaptioned_table(pdf_path)

    paper = enrich_paper(PyMuPDFParser().parse(pdf_path))

    assert len(paper.tables) == 1

    table = paper.tables[0]

    assert table.caption is None
    assert table.detection_source == "layout"
    assert table.page_number == 1
    assert "Accuracy" in table.text


def test_caption_is_matched_to_the_laid_out_table(tmp_path):
    pdf_path = tmp_path / "captioned_grid.pdf"

    create_pdf_with_uncaptioned_table(pdf_path)

    document = pymupdf.open(pdf_path)

    document.load_page(0).insert_text(
        (70, 215),
        "Table 1: Model Performance",
        fontsize=9,
    )

    captioned_path = tmp_path / "captioned.pdf"

    document.save(captioned_path)
    document.close()

    paper = enrich_paper(PyMuPDFParser().parse(captioned_path))

    assert len(paper.tables) == 1

    table = paper.tables[0]

    assert table.caption == "Table 1: Model Performance"
    assert table.detection_source == "caption+layout"
    assert table.row_count and table.row_count >= 3
