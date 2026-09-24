from app.models.paper import Paper, PaperPage, Section, TextBlock
from app.storage.paper_store import (
    PaperStoreError,
    iter_papers,
    load_paper,
    save_paper,
    stored_paper_ids,
)

import pytest


def make_paper(paper_id: str = "abc123") -> Paper:

    block = TextBlock(
        block_id=f"{paper_id}:p1:b0",
        page_number=1,
        start_char=0,
        end_char=11,
        text="Hello world",
        bbox=(0.0, 0.0, 10.0, 10.0),
        block_index=0,
        font_size=12.0,
    )

    return Paper(
        paper_id=paper_id,
        source_path=f"/tmp/{paper_id}.pdf",
        filename=f"{paper_id}.pdf",
        title="A Study of Things",
        abstract="We study things.",
        full_text="Hello world",
        pages=[
            PaperPage(
                page_number=1,
                width=595.0,
                height=842.0,
                blocks=[block],
                text="Hello world",
            )
        ],
        sections=[
            Section(
                section_id=f"{paper_id}:s0",
                heading="Introduction",
                canonical_role="intro",
                page_start=1,
                page_end=1,
                start_char=0,
                end_char=11,
                text="Hello world",
            )
        ],
        page_count=1,
        extracted_char_count=11,
    )


def test_save_and_load_round_trips(tmp_path):

    paper = make_paper()

    path = save_paper(paper, tmp_path)

    assert path.exists()

    loaded = load_paper(paper.paper_id, tmp_path)

    assert loaded.paper_id == paper.paper_id
    assert loaded.title == paper.title
    assert loaded.full_text == paper.full_text

    # Offsets and page numbers must survive the round trip, or stored papers
    # are useless as evidence sources.
    assert loaded.pages[0].blocks[0].start_char == 0
    assert loaded.pages[0].blocks[0].end_char == 11
    assert loaded.pages[0].blocks[0].page_number == 1
    assert loaded.sections[0].canonical_role == "intro"


def test_saving_twice_replaces_and_leaves_no_temp_file(tmp_path):

    paper = make_paper()

    save_paper(paper, tmp_path)

    paper.title = "A Revised Study of Things"

    save_paper(paper, tmp_path)

    assert load_paper(paper.paper_id, tmp_path).title == "A Revised Study of Things"

    assert list(tmp_path.glob("*.tmp")) == []
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_iter_papers_is_sorted_and_ids_are_listed(tmp_path):

    for paper_id in ("ccc", "aaa", "bbb"):
        save_paper(make_paper(paper_id), tmp_path)

    assert [paper.paper_id for paper in iter_papers(tmp_path)] == ["aaa", "bbb", "ccc"]
    assert stored_paper_ids(tmp_path) == ["aaa", "bbb", "ccc"]


def test_missing_store_is_empty_not_an_error(tmp_path):

    missing = tmp_path / "nope"

    assert list(iter_papers(missing)) == []
    assert stored_paper_ids(missing) == []


def test_loading_an_unknown_paper_raises(tmp_path):

    with pytest.raises(PaperStoreError):
        load_paper("missing", tmp_path)
