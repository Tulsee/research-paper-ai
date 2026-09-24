import pymupdf

from app.extraction.section_detector import (
    canonical_role,
    enrich_paper_sections,
)
from app.ingestion.pymupdf_parser import PyMuPDFParser


def create_test_pdf(path):
    document = pymupdf.open()

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


def test_exact_heading_matches_win_over_phrase_matches():

    # "summary" alone is an abstract, but the whole phrase is a conclusion.
    assert canonical_role("Summary") == "abstract"
    assert canonical_role("Summary and Conclusion") == "conclusion"
    assert canonical_role("Summary & Conclusion") == "conclusion"


def test_canonical_roles_survive_real_world_heading_wording():

    # Headings the old exact-only matching silently dropped.
    assert canonical_role("Research Methodology") == "methods"
    assert canonical_role("METHODOLOGY:") == "methods"
    assert canonical_role("3.1 Experimental Setup") == "methods"
    assert canonical_role("Chapter 4 Results") == "results"
    assert canonical_role("Literature Review") == "related_work"


def test_prose_is_not_forced_into_a_canonical_role():

    assert canonical_role("Case Study") is None
    assert canonical_role("Technical Development") is None
    assert canonical_role("") is None

    # Long enough to be prose rather than a section label, even though it
    # contains the word "review".
    assert (
        canonical_role(
            "The research gap and positioning This review identifies four gaps."
        )
        is None
    )


def test_generic_words_only_count_as_roles_when_they_are_the_whole_heading():

    # These map only as complete headings...
    assert canonical_role("Analysis") == "discussion"
    assert canonical_role("Findings") == "results"
    assert canonical_role("Background") == "intro"

    # ...and never as a word inside a longer phrase, or a title like
    # "Machine Learning for Tourism Migration Analysis" would be mistaken
    # for a section heading and dropped.
    assert canonical_role("Sentiment Analysis") is None
    assert canonical_role("Machine Learning for Tourism Migration Analysis") is None
    assert canonical_role("Background and Related Work") == "related_work"
