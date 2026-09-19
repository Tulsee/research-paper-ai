import fitz

from app.extraction.section_detector import (
    enrich_paper_sections,
)
from app.ingestion.pymupdf_parser import PyMuPDFParser


def create_test_pdf(path):
    document = fitz.open()

    page = document.new_page()

    title = "Machine Learning for Tourism Migration Analysis"

    page.insert_text(
        (70, 70),
        title,
        fontsize=20,
        fontname="hebo",
    )

    page.insert_text(
        (70, 120),
        "Abstract",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 145),
        "This study investigates migration patterns using machine learning.",
        fontsize=10,
    )

    page.insert_text(
        (70, 190),
        "1 Introduction",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 215),
        "Migration is an important socioeconomic phenomenon.",
        fontsize=10,
    )

    page.insert_text(
        (70, 260),
        "2 Related Work",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 285),
        "Previous studies have investigated migration and tourism.",
        fontsize=10,
    )

    page.insert_text(
        (70, 330),
        "3 Methodology",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 355),
        "The proposed methodology uses machine learning models.",
        fontsize=10,
    )

    page.insert_text(
        (70, 400),
        "4 Results",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 425),
        "The experimental results demonstrate useful patterns.",
        fontsize=10,
    )

    page.insert_text(
        (70, 470),
        "5 Conclusion",
        fontsize=14,
        fontname="hebo",
    )

    page.insert_text(
        (70, 495),
        "The study concludes that machine learning can support analysis.",
        fontsize=10,
    )

    document.save(path)
    document.close()


def test_section_detection(tmp_path):
    pdf_path = tmp_path / "section_test.pdf"

    create_test_pdf(pdf_path)

    parser = PyMuPDFParser()

    paper = parser.parse(pdf_path)

    paper = enrich_paper_sections(paper)

    assert paper.title == ("Machine Learning for Tourism Migration Analysis")

    assert paper.abstract is not None

    roles = [section.canonical_role for section in paper.sections]

    assert "abstract" in roles
    assert "intro" in roles
    assert "related_work" in roles
    assert "methods" in roles
    assert "results" in roles
    assert "conclusion" in roles


def test_section_offsets(tmp_path):
    pdf_path = tmp_path / "offset_test.pdf"

    create_test_pdf(pdf_path)

    parser = PyMuPDFParser()

    paper = parser.parse(pdf_path)

    paper = enrich_paper_sections(paper)

    for section in paper.sections:
        extracted = paper.full_text[section.start_char : section.end_char]

        assert extracted.strip() == section.text.strip()
