from app.extraction.layout_extractor import (
    extract_tables_and_figures,
)

from app.extraction.reference_parser import (
    parse_references,
)

from app.extraction.section_detector import (
    enrich_paper_sections,
)


def enrich_paper(paper):

    # ----------------------------------------
    # 1. Sections + title + abstract
    # ----------------------------------------

    paper = enrich_paper_sections(paper)

    # ----------------------------------------
    # 2. Tables + figures
    # ----------------------------------------

    tables, figures, warnings = extract_tables_and_figures(paper)

    paper.tables = tables
    paper.figures = figures

    paper.warnings.extend(warnings)

    # ----------------------------------------
    # 3. References
    # ----------------------------------------

    references, warnings = parse_references(paper)

    paper.references = references

    paper.warnings.extend(warnings)

    return paper
