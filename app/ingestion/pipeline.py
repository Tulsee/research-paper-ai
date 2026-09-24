from pathlib import Path

from app.chunking.section_chunker import (
    SectionChunker,
)

from app.extraction.enrich_paper import (
    enrich_paper,
)

from app.ingestion.pymupdf_parser import (
    PyMuPDFParser,
)


def process_pdf(
    pdf_path: str | Path,
):

    # -----------------------------------
    # Stage 1: Parse PDF
    # -----------------------------------

    parser = PyMuPDFParser()

    paper = parser.parse(pdf_path)

    # -----------------------------------
    # Stage 2: Extract structure
    # -----------------------------------

    paper = enrich_paper(paper)

    # -----------------------------------
    # Stage 3: Chunk
    # -----------------------------------

    chunker = SectionChunker()

    paper = chunker.chunk_paper(paper)

    return paper
