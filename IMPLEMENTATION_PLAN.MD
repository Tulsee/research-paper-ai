# Research Paper AI — Implementation Plan

**Goal:** Turn a set of research papers into verified analyses, an evidence-backed gap report, and a draftable PhD proposal — where every factual claim traces back to a page and passage in a real paper.

**Non-goals (v1):** no automatic paper discovery/crawling, no multi-user accounts, no fine-tuning, no non-PDF inputs (LaTeX/HTML sources come later).

**Guiding constraint:** the system must never state a fact it cannot cite. Grounding is a hard requirement, not a quality metric — every stage below carries evidence forward rather than summarising it away.

## Stack decisions

| Layer             | Choice                                                  | Notes                                                                 |
| ----------------- | ------------------------------------------------------- | --------------------------------------------------------------------- |
| Language          | Python 3.11+                                            |                                                                       |
| PDF parsing       | PyMuPDF (+ PyMuPDF4LLM for layout-aware markdown)       | GROBID as a stage-1 upgrade for references/affiliations               |
| LLM               | Anthropic API,`claude-opus-5`                           | adaptive thinking;`claude-sonnet-5` for bulk/judge passes only        |
| Structured output | `output_config.format` (JSON schema) + Pydantic mirrors | never parse prose into fields                                         |
| Vector store      | ChromaDB (local, v1) → Qdrant if the corpus outgrows it | keep the store behind a`Retriever` interface so this swap is one file |
| Lexical search    | BM25 (`rank_bm25`)                                      | hybrid with dense, fused by RRF                                       |
| Reranker          | cross-encoder (`bge-reranker-v2-m3`)                    |                                                                       |
| Metadata/state    | SQLite + SQLAlchemy                                     | papers, analyses, runs, eval results                                  |
| API               | FastAPI                                                 |                                                                       |
| UI                | Streamlit (v1) → React/Next.js if it outgrows it        |                                                                       |

## Cross-cutting foundations

These are not a stage — they are built in stage 0 and touched by every stage after.

### Data model

Define these as Pydantic models in `schemas.py` **before writing stage 1**. Every later stage consumes and produces them.

- `Evidence` — `paper_id`, `chunk_id`, `section`, `page`, `char_span`, `quoted_text`. The atom of the whole system.
- `Paper` — `paper_id`, metadata (title, authors, year, venue, DOI), `sections[]` (heading, level, paragraphs), `tables[]`, `figures[]`, `references[]`, `page_count`, `warnings[]`.
- `Chunk` — `chunk_id`, `paper_id`, `section`, `page`, `text`, `embedding_ref`.
- `PaperAnalysis` — every field is `{value, evidence[], status}` where `status ∈ {stated, inferred, not_stated}`. A bare string field anywhere in this model is a bug.
- `GapReport`, `Proposal` — same `{value, evidence[]}` discipline.

### LLM layer (`llm.py`)

One module wraps all Anthropic calls; no stage calls the SDK directly.

- Model `claude-opus-5`, `thinking={"type": "adaptive"}`, streaming with `.get_final_message()` for anything long.
- Structured output via `output_config={"format": {...}}` — not prompt-and-hope JSON.
- **Prompt caching** on the system prompt and the paper text: a long paper analysed across several section-wise calls should hit cache on every call after the first. Verify with `usage.cache_read_input_tokens` — if it stays zero, something volatile (a timestamp, an unsorted dict) is sitting in the cached prefix.
- **Batch API** for corpus-wide passes (bulk extraction, embedding prep, eval runs) — asynchronous, 50% cost.
- Log `usage` per call into SQLite so cost per paper is a number you can look up, not a surprise.
- Every call records `{prompt_version, model, params}` on its output — stage 3 cannot measure a regression without knowing what changed.

### Repo skeleton (stage 0)

`ingest/`, `analysis/`, `retrieval/`, `synthesis/`, `proposal/`, `eval/`, `api/`, `ui/`, `schemas.py`, `llm.py`, `storage.py`, `tests/`. Pin dependencies, add pytest + ruff, commit a `.env.example` with `ANTHROPIC_API_KEY`.

---

## Stage 1 — Document ingestion and parsing

**Purpose:** Convert a PDF into a reliable, structured research-paper object.

**Input:** PDF file.
**Output:** `Paper` object with metadata, sections, paragraphs, tables, figures, references, page numbers, and extraction warnings.

**Build:**

1. Text + layout extraction with PyMuPDF; keep page number and character offset on every block — these are what `Evidence` points at, so losing them here is unrecoverable downstream.
2. Section tree from heading detection (font size/weight + numbering patterns), normalised to canonical roles: abstract, intro, related work, methods, results, discussion, conclusion, references.
3. Table and figure-caption extraction; on failure record a warning rather than dropping content silently.
4. Reference parsing — regex/heuristic in v1, GROBID once reference quality starts limiting stage 5.
5. Chunking for stage 4: section-aware, ~800 tokens with ~15% overlap, never crossing a section boundary, each chunk carrying `section` + `page`.

**Done when:** on a 20-paper dev set spanning ≥3 publishers, ≥95% have correct title and abstract, ≥90% have a correct canonical section tree, every extracted block resolves to a page number, and papers that fail produce a warning rather than a silently truncated `Paper`.

**Risk:** two-column and scanned PDFs. Decide explicitly whether v1 OCRs (Tesseract) or rejects scanned PDFs with a clear error — rejecting is the right v1 call.

---

## Stage 2 — Single-paper scientific analysis

**Purpose:** Extract what the authors actually did, found, and concluded.

**Input:** `Paper`.
**Output:** `PaperAnalysis`, every field evidence-backed.

**Build:**

1. Section-routed extraction — abstract+intro for research problem and contribution, methods for design/dataset/baselines, results for numeric findings, discussion+conclusion for interpretation and stated limitations. Long papers are analysed per section, not in one call.
2. Force structured output against the `PaperAnalysis` schema.
3. **Grounding:** require a verbatim quote plus page for every field, then verify the quote by string-matching it back into the `Paper` text. A quote that does not match is a hallucination — drop the field to `not_stated` and log it. This check is cheap and catches the exact failure mode the whole project depends on avoiding.
4. Mark absent information `not_stated` and model-derived claims `inferred`; never let an inference occupy the same status as a stated fact.
5. Consider PDF document blocks with `citations: {enabled: true}` as a parallel path — the API returns page-located citations directly, a useful cross-check against the parsed-text path.

**Done when:** on the dev set, ≥98% of `stated` fields pass verbatim quote verification, and unanswerable fields come back `not_stated` rather than fabricated — test this deliberately with papers that omit, say, dataset size.

---

## Stage 3 — Evaluation and evidence verification

**Purpose:** Measure extraction quality and make prompt/model changes a measurable decision rather than a vibe.

**Start this as soon as stage 2 produces its first output — it is continuous, not a phase.**

**Input:** `PaperAnalysis` + a hand-labelled gold standard.
**Output:** field-level accuracy, claim-support score, extraction quality, evaluation report.

**Build:**

1. Hand-label 20–30 papers. This is the single most valuable and most-likely-to-be-skipped task in the plan; budget real hours for it.
2. Deterministic metrics first: field-level exact/fuzzy match, quote-verification pass rate, `not_stated` precision/recall. These need no LLM and never drift.
3. LLM judge (`claude-sonnet-5`) only for what deterministic metrics cannot score — semantic equivalence of free-text fields. Validate the judge against the human labels before trusting it; an unvalidated judge measures nothing.
4. `eval/run.py` writes a timestamped report keyed by `{prompt_version, model, params}`; a comparison mode diffs two runs per field.

**Done when:** rerunning after a prompt or model change produces a per-field improved/regressed/unchanged verdict, and the judge's agreement with human labels is measured and stated.

---

## Stage 4 — Research corpus and hybrid RAG

**Purpose:** Retrieve relevant evidence across multiple papers.

**Input:** many `Paper` objects.
**Output:** ranked passages carrying `paper_id`, title, section, page, `chunk_id`.

**Build:**

1. Embed stage-1 chunks; store vectors in ChromaDB with full metadata attached — metadata loss here breaks citations in stages 5 and 6.
2. BM25 index over the same chunks.
3. Hybrid retrieval: dense + BM25 fused by reciprocal rank fusion, then cross-encoder rerank of the top ~50 down to top ~10.
4. Metadata filters: year, venue, paper set.
5. Retrieval eval set: 30 hand-written cross-paper questions with known correct supporting chunks.

**Done when:** recall@10 ≥ 0.8 and MRR ≥ 0.6 on that eval set, and every returned passage round-trips to the correct page of the correct source PDF.

---

## Stage 5 — Cross-paper synthesis and gap analysis

**Purpose:** Identify recurring limitations, methodological disagreements, underexplored areas, and research opportunities.

**Input:** `PaperAnalysis` records + retrieved evidence.
**Output:** structured literature synthesis + evidence-backed gap report.

**Build:**

1. Cluster analyses by research problem and method family.
2. Build a comparison matrix (method × dataset × metric × result) from `PaperAnalysis` fields alone — no free-text LLM summarising at this step.
3. Derive gap candidates from three distinct sources, and label each gap with which one it came from:
   - **stated** — limitations/future work the authors wrote themselves (strongest);
   - **contradiction** — papers disagreeing on the same question;
   - **absence** — an empty cell in the comparison matrix.
4. Treat absence carefully: your corpus not containing something is not evidence the field has not done it. Every absence-derived gap is flagged _corpus-limited_ until checked against external literature. This is the stage's main failure mode.
5. Every gap carries ≥2 supporting `Evidence` items or it is dropped.

**Done when:** a domain reviewer rates ≥70% of the top-10 gaps as genuine and supported by the cited passages, and every gap displays its type and its corpus-limited flag. Record the reviewer's per-gap verdicts — that becomes the regression set for this stage.

---

## Stage 6 — PhD proposal generation

**Purpose:** Turn a verified gap report into a coherent, feasible research proposal.

**Input:** gap report, paper analyses, optionally verified external literature.
**Output:** proposal with title, background, problem statement, research questions, objectives, methodology, expected contribution, timeline, references.

**Build:**

1. Generate section by section, each conditioned on the specific gap and its evidence — not on a summary of the corpus.
2. **References come only from the corpus.** Build the bibliography from stored `Paper` metadata by ID; the model never writes a citation string. This structurally eliminates fabricated references, the highest-severity failure this system can produce.
3. Require the methodology section to state explicitly how it addresses the named gap, plus its assumptions and limitations.
4. Final validation pass: every citation resolves to a real `paper_id` in the corpus; every literature claim carries `Evidence`; unsupported sentences are flagged for the user, not silently emitted.

**Done when:** zero fabricated references across 10 generated proposals — pass/fail, not a percentage — and an academic reviewer can name the assumptions and limitations from the text alone.

---

## Stage 7 — Web interface

**Purpose:** Make the workflow usable without the command line.

**Input:** uploaded papers and user actions.
**Output:** analysis reports, evidence citations, gap reports, downloadable proposals.

**Build:**

1. FastAPI endpoints over stages 1–6, with long jobs run as background tasks plus a status-polling endpoint — parsing plus analysis exceeds any reasonable HTTP timeout.
2. Streamlit UI: upload → analysis view → library → gap report → proposal export (Markdown/DOCX).
3. **Every displayed claim is click-through to its source page.** If the UI shows text that cannot be traced, the stage is not done.
4. Surface extraction warnings and `not_stated` fields rather than hiding them.

**Done when:** a user uploads a paper, analyses it, adds it to the library, generates a gap report, exports a proposal, and can click any claim to reach the highlighted source page.

---

## Build order

Stage 0 → 1 → 2 → **3 (then continuously)** → 4 → 5 → 6 → 7.

Two ordering notes. Stage 3 starts right after stage 2's first output and runs forever after — building 4–6 on unmeasured extraction means you cannot tell which stage a bad gap report came from. Stage 7 can begin as a thin UI over stages 1–2 in parallel with stage 4, since it depends on the schemas rather than on retrieval quality.

**Milestones:** M1 = stages 0–1 (PDF → `Paper`). M2 = stages 2–3 (analysis with measured quality). M3 = stages 4–5 (corpus → gap report). M4 = stages 6–7 (proposal + UI).

## Top risks

| Risk                                              | Mitigation                                                                                          |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Gold-standard labelling gets skipped              | It is M2's exit criterion; nothing downstream is trustworthy without it                             |
| Hallucinated citations in the proposal            | Bibliography built from stored metadata by ID; the model never writes a citation string (stage 6.2) |
| "Gaps" that are only corpus holes                 | Gap typing + corpus-limited flag (stage 5.3–5.4)                                                    |
| Parser quality silently degrading the whole chain | Extraction warnings surfaced, quote verification in stage 2.3                                       |
| Cost growth on long papers                        | Prompt caching, Batch API, per-paper cost logged from day one                                       |
