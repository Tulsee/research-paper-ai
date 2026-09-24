from typing import Any

from pydantic import BaseModel, Field


class Table(BaseModel):
    table_id: str

    caption: str | None = None

    page_number: int

    bbox: tuple[float, float, float, float] | None = None

    text: str = ""

    start_char: int | None = None
    end_char: int | None = None

    # "caption"         -> found via a "Table N ..." caption only
    # "layout"          -> found via PDF layout analysis only
    # "caption+layout"  -> caption matched to a laid-out table
    detection_source: str = "caption"

    row_count: int | None = None
    col_count: int | None = None


class Figure(BaseModel):
    figure_id: str

    caption: str | None = None

    page_number: int

    bbox: tuple[float, float, float, float] | None = None

    text: str = ""

    start_char: int | None = None
    end_char: int | None = None

    # "caption"         -> found via a "Figure N ..." caption only
    # "layout"          -> found via an embedded image only
    # "caption+layout"  -> caption matched to an embedded image
    detection_source: str = "caption"


class Reference(BaseModel):
    reference_id: str

    number: int | None = None

    raw_text: str

    authors: list[str] = Field(default_factory=list)

    title: str | None = None

    year: int | None = None


class TextBlock(BaseModel):
    block_id: str
    page_number: int

    start_char: int
    end_char: int

    text: str

    bbox: tuple[float, float, float, float]

    block_index: int
    block_type: int = 0

    # Layout information used for heading detection
    font_size: float | None = None
    font_name: str | None = None
    is_bold: bool = False


class PaperPage(BaseModel):
    page_number: int

    width: float
    height: float

    blocks: list[TextBlock] = Field(default_factory=list)

    text: str = ""

    # Number of image blocks on the page. A page with images but no
    # text blocks is typically a scanned cover page.
    image_count: int = 0


class Section(BaseModel):
    section_id: str

    heading: str
    canonical_role: str | None = None

    level: int = 1

    page_start: int
    page_end: int

    start_char: int
    end_char: int

    text: str = ""

    parent_id: str | None = None


class Chunk(BaseModel):
    chunk_id: str

    text: str

    token_count: int

    section_id: str
    section_heading: str
    canonical_role: str | None = None

    page_start: int
    page_end: int

    start_char: int
    end_char: int

    chunk_index: int


class Paper(BaseModel):
    schema_version: str = "1.0"

    paper_id: str

    source_path: str
    filename: str

    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    abstract: str | None = None

    full_text: str = ""

    pages: list[PaperPage] = Field(default_factory=list)

    sections: list[Section] = Field(default_factory=list)

    tables: list[Table] = Field(default_factory=list)

    figures: list[Figure] = Field(default_factory=list)

    references: list[Reference] = Field(default_factory=list)

    chunks: list[Chunk] = Field(default_factory=list)

    # Raw document metadata as reported by the PDF (title, author, ...).
    pdf_metadata: dict[str, Any] = Field(default_factory=dict)

    parser: str = "pymupdf"
    parser_version: str | None = None

    warnings: list[str] = Field(default_factory=list)

    page_count: int = 0
    extracted_char_count: int = 0
