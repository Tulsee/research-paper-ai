import pymupdf

from app.extraction.enrich_paper import enrich_paper
from app.ingestion.pymupdf_parser import PyMuPDFParser


def create_test_pdf(path):

    document = pymupdf.open()

    page = document.new_page()

    page.insert_text(
        (70, 60),
        "A Machine Learning Study",
        fontsize=20,
        fontname="hebo",
    )

    page.insert_text(
        (70, 100),
        "Abstract",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 125),
        "This paper presents a machine learning study.",
        fontsize=10,
    )

    page.insert_text(
        (70, 170),
        "1 Introduction",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 195),
        "Machine learning is widely used in research.",
        fontsize=10,
    )

    page.insert_text(
        (70, 240),
        "2 Methodology",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 265),
        "We evaluate several machine learning models.",
        fontsize=10,
    )

    page.insert_text(
        (70, 310),
        "Table 1: Model Performance",
        fontsize=10,
        fontname="hebo",
    )

    page.insert_text(
        (70, 355),
        "Figure 1: Proposed Architecture",
        fontsize=10,
        fontname="hebo",
    )

    page.insert_text(
        (70, 400),
        "3 Results",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 425),
        "The results demonstrate improved performance.",
        fontsize=10,
    )

    page.insert_text(
        (70, 470),
        "4 References",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 495),
        "[1] Smith, J. 2024. Machine Learning Research.",
        fontsize=10,
    )

    page.insert_text(
        (70, 520),
        "[2] Jones, A. 2023. Artificial Intelligence Methods.",
        fontsize=10,
    )

    document.save(path)
    document.close()


def test_full_extraction_pipeline(tmp_path):

    pdf_path = tmp_path / "test.pdf"

    create_test_pdf(pdf_path)

    parser = PyMuPDFParser()

    paper = parser.parse(pdf_path)

    paper = enrich_paper(paper)

    assert paper.title == ("A Machine Learning Study")

    assert paper.abstract is not None

    assert len(paper.sections) >= 5

    assert len(paper.tables) == 1

    assert len(paper.figures) == 1

    assert len(paper.references) == 2


def test_reference_numbers(tmp_path):

    pdf_path = tmp_path / "references.pdf"

    create_test_pdf(pdf_path)

    paper = PyMuPDFParser().parse(pdf_path)

    paper = enrich_paper(paper)

    numbers = [reference.number for reference in paper.references]

    assert numbers == [1, 2]


def test_table_caption(tmp_path):

    pdf_path = tmp_path / "tables.pdf"

    create_test_pdf(pdf_path)

    paper = PyMuPDFParser().parse(pdf_path)

    paper = enrich_paper(paper)

    assert paper.tables[0].caption == ("Table 1: Model Performance")


def test_figure_caption(tmp_path):

    pdf_path = tmp_path / "figures.pdf"

    create_test_pdf(pdf_path)

    paper = PyMuPDFParser().parse(pdf_path)

    paper = enrich_paper(paper)

    assert paper.figures[0].caption == ("Figure 1: Proposed Architecture")
