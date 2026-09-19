from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    """A text block extracted from a single PDF page."""

    block_id: str

    page_number: int = Field(ge=1)

    # Text position within Paper.full_text.
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)

    text: str

    # PDF coordinates in points: x0, y0, x1, y1.
    bbox: tuple[float, float, float, float]

    # Reading-order index on the page.
    block_index: int = Field(ge=0)

    # PyMuPDF block type: 0 generally means text.
    block_type: int = Field(ge=0)


class PaperPage(BaseModel):
    """Normalized information extracted from one PDF page."""

    page_number: int = Field(ge=1)

    width: float = Field(gt=0)
    height: float = Field(gt=0)

    blocks: list[TextBlock] = Field(default_factory=list)

    # The normalized text belonging to this page.
    text: str = ""


class Paper(BaseModel):
    """Normalized research-paper document."""

    schema_version: str = "1.0"

    paper_id: str
    source_path: str

    filename: str

    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    abstract: Optional[str] = None

    # Full normalized text, used by later modules.
    full_text: str

    pages: list[PaperPage] = Field(default_factory=list)

    # These will be populated in later milestones.
    sections: list = Field(default_factory=list)
    references: list = Field(default_factory=list)
    tables: list = Field(default_factory=list)
    figures: list = Field(default_factory=list)

    parser_name: str
    parser_version: str

    warnings: list[str] = Field(default_factory=list)

    page_count: int = Field(ge=0)
    extracted_char_count: int = Field(ge=0)
