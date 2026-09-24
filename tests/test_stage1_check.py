import json

from app.eval.stage1_check import (
    canonical_role_sequence,
    check_invariants,
    init_gold,
    load_gold,
    run,
    score_abstract,
    score_sections,
    score_title,
)
from app.models.paper import Chunk
from app.storage.paper_store import save_paper

from tests.test_paper_store import make_paper


def add_chunk(paper, **overrides):

    section = paper.sections[0]

    fields = dict(
        chunk_id=f"{paper.paper_id}:chunk_0",
        text=paper.full_text[section.start_char : section.end_char],
        token_count=2,
        section_id=section.section_id,
        section_heading=section.heading,
        canonical_role=section.canonical_role,
        page_start=1,
        page_end=1,
        start_char=section.start_char,
        end_char=section.end_char,
        chunk_index=0,
    )

    fields.update(overrides)

    paper.chunks.append(Chunk(**fields))

    return paper


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_a_well_formed_paper_has_no_invariant_failures():

    paper = add_chunk(make_paper())

    assert check_invariants(paper) == []


def test_block_offsets_that_do_not_round_trip_are_caught():

    paper = make_paper()

    paper.pages[0].blocks[0].end_char = 5

    failures = check_invariants(paper)

    assert any("round-trip" in failure for failure in failures)


def test_a_chunk_escaping_its_section_is_caught():

    paper = make_paper()

    # Section spans 0:11; this chunk reaches past its end.
    paper = add_chunk(paper, end_char=40, text=paper.full_text)

    failures = check_invariants(paper)

    assert any("escapes its section" in failure for failure in failures)


def test_a_chunk_page_outside_the_paper_is_caught():

    paper = add_chunk(make_paper(), page_end=99)

    failures = check_invariants(paper)

    assert any("outside the paper" in failure for failure in failures)


def test_a_chunk_on_an_unknown_section_is_caught():

    paper = add_chunk(make_paper(), section_id="not-a-section")

    failures = check_invariants(paper)

    assert any("unknown section" in failure for failure in failures)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_title_scoring_ignores_case_punctuation_and_spacing():

    paper = make_paper()

    assert score_title(paper, {"title": "A Study of Things"}) is True
    assert score_title(paper, {"title": "a  study, of things."}) is True
    assert score_title(paper, {"title": "An Unrelated Paper"}) is False


def test_abstract_scoring_matches_a_verbatim_prefix():

    paper = make_paper()

    assert score_abstract(paper, {"abstract_prefix": "We study things."}) is True
    assert score_abstract(paper, {"abstract_prefix": "We study"}) is True
    assert score_abstract(paper, {"abstract_prefix": "We ignore things."}) is False


def test_a_missing_abstract_scores_wrong_not_skipped():

    paper = make_paper()

    paper.abstract = None

    assert score_abstract(paper, {"abstract_prefix": "We study things."}) is False


def test_unscorable_gold_fields_are_skipped_not_failed():

    paper = make_paper()

    assert score_title(paper, {}) is None
    assert score_abstract(paper, {}) is None
    assert score_sections(paper, {}) is None


def test_section_scoring_reports_missing_and_extra_roles():

    paper = make_paper()

    assert canonical_role_sequence(paper) == ["intro"]

    matched, missing, extra = score_sections(paper, {"canonical_roles": ["intro"]})

    assert matched is True
    assert missing == []
    assert extra == []

    matched, missing, extra = score_sections(
        paper,
        {"canonical_roles": ["abstract", "intro", "methods"]},
    )

    assert matched is False
    assert missing == ["abstract", "methods"]
    assert extra == []


# ---------------------------------------------------------------------------
# Gold labels and the run report
# ---------------------------------------------------------------------------


def test_unverified_gold_labels_are_ignored(tmp_path):

    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()

    label = {"paper_id": "abc123", "verified": False, "title": "A Study of Things"}

    (gold_dir / "abc123.json").write_text(json.dumps(label), encoding="utf-8")

    assert load_gold("abc123", gold_dir) is None

    label["verified"] = True

    (gold_dir / "abc123.json").write_text(json.dumps(label), encoding="utf-8")

    assert load_gold("abc123", gold_dir)["title"] == "A Study of Things"


def test_init_gold_templates_are_unverified(tmp_path):

    store = tmp_path / "store"
    gold = tmp_path / "gold"

    save_paper(add_chunk(make_paper()), store)

    assert init_gold(store, gold) == 0

    template = json.loads((gold / "abc123.json").read_text(encoding="utf-8"))

    # A bootstrapped template must never count as a label, or the parser
    # would be scoring itself against its own output.
    assert template["verified"] is False
    assert template["title"] == "A Study of Things"
    assert template["canonical_roles"] == ["intro"]

    assert load_gold("abc123", gold) is None


def test_init_gold_does_not_overwrite_existing_labels(tmp_path):

    store = tmp_path / "store"
    gold = tmp_path / "gold"
    gold.mkdir()

    save_paper(make_paper(), store)

    existing = {"paper_id": "abc123", "verified": True, "title": "Hand written"}

    (gold / "abc123.json").write_text(json.dumps(existing), encoding="utf-8")

    init_gold(store, gold)

    assert load_gold("abc123", gold)["title"] == "Hand written"


def test_run_fails_on_an_empty_store(tmp_path, capsys):

    assert run(tmp_path / "store", tmp_path / "gold") == 1

    assert "No stored papers" in capsys.readouterr().out


def test_run_fails_when_there_are_no_verified_labels(tmp_path, capsys):

    store = tmp_path / "store"

    save_paper(add_chunk(make_paper()), store)

    assert run(store, tmp_path / "gold") == 1

    output = capsys.readouterr().out

    assert "without a verified gold label" in output
    assert "accuracy was not measured" in output


def test_run_passes_on_a_correctly_labelled_paper(tmp_path, capsys):

    store = tmp_path / "store"
    gold = tmp_path / "gold"
    gold.mkdir()

    save_paper(add_chunk(make_paper()), store)

    (gold / "abc123.json").write_text(
        json.dumps(
            {
                "paper_id": "abc123",
                "verified": True,
                "title": "A Study of Things",
                "abstract_prefix": "We study things.",
                "canonical_roles": ["intro"],
            }
        ),
        encoding="utf-8",
    )

    assert run(store, gold) == 0

    output = capsys.readouterr().out

    assert "FAIL" not in output

    # One paper is a smoke test, not the stage-1 exit criterion.
    assert "not the exit criterion" in output


def test_run_fails_on_a_mislabelled_paper(tmp_path, capsys):

    store = tmp_path / "store"
    gold = tmp_path / "gold"
    gold.mkdir()

    save_paper(add_chunk(make_paper()), store)

    (gold / "abc123.json").write_text(
        json.dumps(
            {
                "paper_id": "abc123",
                "verified": True,
                "title": "A Completely Different Title",
                "abstract_prefix": "Nothing like the abstract.",
                "canonical_roles": ["abstract", "methods"],
            }
        ),
        encoding="utf-8",
    )

    assert run(store, gold) == 1

    assert "FAIL" in capsys.readouterr().out


def test_run_fails_when_invariants_break(tmp_path, capsys):

    store = tmp_path / "store"
    gold = tmp_path / "gold"
    gold.mkdir()

    paper = add_chunk(make_paper(), page_end=99)

    save_paper(paper, store)

    (gold / "abc123.json").write_text(
        json.dumps(
            {
                "paper_id": "abc123",
                "verified": True,
                "title": "A Study of Things",
                "abstract_prefix": "We study things.",
                "canonical_roles": ["intro"],
            }
        ),
        encoding="utf-8",
    )

    assert run(store, gold) == 1

    assert "INVARIANT" in capsys.readouterr().out
