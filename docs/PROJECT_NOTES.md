# MOSFET Selection RAG App — build notes

> This file is a committed, version-controlled mirror of the AI coding
> assistant's working memory for this project (previously only stored
> in a local, machine-scoped, non-git-tracked location). It exists so
> that project context/history survives account switches, machine
> changes, or the assistant's memory being cleared. **Keep this file
> updated going forward** (append new entries at the end) any time
> significant implementation decisions, bugs, or review findings occur
> — treat it as the durable, canonical build log, not the tool-specific
> memory store.

Spec source: `Planning/Step 2 SPEC MD to Code/SPEC.MD` (outside the `code`
workspace root). Project root = workspace root
`c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code`. This is a
multi-turn, file-by-file implementation of that spec (Python 3.11 project).

## Files created so far
- `src/__init__.py`, `src/db/__init__.py` — empty packages.
- `src/config.py` — paths ONLY so far (BASE_DIR, DATA_DIR, RAW_DIR,
  MODELS_DIR, EMBEDDING_MODEL_DIR, RERANKER_MODEL_DIR, KNOWLEDGE_DB,
  MONITORING_DB, GROUND_TRUTH_CSV, RETRIEVAL_EVAL_RESULTS_JSON/CSV).
  Calls `load_dotenv()` at import time. Still needs (add when those
  layers are implemented): model IDs, TOP_K/FINAL_N/ALPHA/RRF_K,
  ACTIVE_RETRIEVAL_APPROACH/ACTIVE_ALPHA (writable, overwritten by
  eval-retrieval per spec §11.3), pricing table, default LLM provider.
- `src/db/knowledge_store.py` — connection mgmt + schema init only
  (per spec §5.1). Public API: `get_connection()`, `connect()`
  (contextmanager), `init_db()`, `EMBEDDING_DIM` (=384, for
  multi-qa-MiniLM-L6-cos-v1). No query/retrieval functions in this file
  by design — those belong in `src/retrieval/`.
- `requirements.txt` — pinned so far: `python-dotenv==1.2.3`,
  `sqlite-vec==0.1.9`, `dlt==1.30.0`, `pymupdf==1.28.2`. Append (don't
  replace) as new files are added. dlt/pymupdf versions ARE verified
  against PyPI's JSON API (fetched `pypi.org/pypi/<pkg>/json` directly)
  as the latest non-yanked releases, both compatible with Python 3.11
  (spec's pin). Note: dlt 1.27.0/1.27.1 were yanked for an incremental-
  merge data-loss bug — irrelevant here since our custom
  `@dlt.destination` bypasses dlt's merge/upsert logic entirely.
- `src/ingestion/` (new package: `__init__.py`, `pdf_extractor.py`,
  `resources.py`, `pipeline.py`) — dlt ingestion pipeline per spec §8.
  - `pdf_extractor.extract_first_page_fields(pdf_path)`: opens PDF with
    `fitz`, reads ONLY `doc[0]` (first page), extracts component_type/
    manufacturer_name/part_number via regex/lookup heuristics and
    descriptions/features/applications via heading-based line scanning.
    Never raises — returns all-empty dict on any failure. Builds
    `search_text` by joining only the sections actually found.
  - `resources.datasheet_records()`: `@dlt.resource(name="master_table")`
    globs `RAW_DIR/*.pdf`, calls extractor, embeds `search_text` via
    `src.models_onnx.embedder.embed()` (module doesn't exist yet —
    future dependency, assumed per spec), yields ONLY the 5 fields
    (no `id`): component_type, manufacturer_name, part_number,
    search_text, search_vector (list[float] | None).
  - `pipeline.py`: custom `@dlt.destination` sink
    (`knowledge_store_destination`, batch_size=1) that bypasses dlt's
    SQL client entirely — opens `src.db.knowledge_store.connect()` and
    runs raw parameterized INSERT into `master_table` (explicit 5
    columns), wrapping vectors with `sqlite_vec.serialize_float32()`.
    This avoids dlt inferring/mutating the hand-authored schema.
    `run()` calls `init_db()` then `pipeline.run(datasheet_records())`.
    `__main__` entry point for `make ingest`.
  - Confirmed dlt custom-destination API via docs fetch: decorator
    signature `@dlt.destination(batch_size, loader_file_format, name,
    skip_dlt_columns_and_tables=True by default)`, function signature
    `(items: TDataItems, table: TTableSchema) -> None`, imports from
    `dlt.common.typing` and `dlt.common.schema`.

## Verified technical facts
- `sqlite_vec.load(conn)` requires
  `conn.enable_load_extension(True)` before and `(False)` after — this
  is the correct, confirmed-working pattern (smoke-tested).
- vec0 virtual tables support an explicit rowid alias:
  `CREATE VIRTUAL TABLE x USING vec0(id INTEGER PRIMARY KEY, col FLOAT[N])`.
- FTS5 external-content tables (`content='master_table', content_rowid='id'`)
  need the special `INSERT INTO fts_tbl(fts_tbl, rowid, ...) VALUES('delete', ...)`
  form in AFTER DELETE/UPDATE triggers — confirmed working via smoke test
  (`init_db(':memory:')` ran clean end-to-end incl. all 6 triggers).
- Embedding dim for `sentence-transformers/multi-qa-MiniLM-L6-cos-v1` = 384
  (confirmed on HF model card).
- Smoke-testing approach used: temp venv under `$env:TEMP`, pip install
  pinned deps, run a quick `-c` import/init check, then delete the venv.
  User skipped a more elaborate smoke-test-file approach — prefer the
  lighter inline `-c` check unless asked for deeper verification.

## src/models_onnx/ (new package, spec §7)
- `__init__.py`, `export.py`, `embedder.py`, `reranker.py`.
- `export.py`: `export_embedding_model()`/`export_reranker_model()`/`export_all()`
  using `optimum.onnxruntime.ORTModelForFeatureExtraction` /
  `ORTModelForSequenceClassification` (`from_pretrained(model_id, export=True)`)
  + `AutoTokenizer`, saving both to `config.EMBEDDING_MODEL_DIR` /
  `RERANKER_MODEL_DIR`. `__main__` entrypoint for `make export-models`.
- `embedder.py`: `embed(texts) -> np.ndarray`, lazy-cached ONNX session +
  tokenizer, mean-pool over attention mask + L2-normalize (cosine-ready).
  Raises `FileNotFoundError` with a clear message if `model.onnx` missing
  (i.e. export hasn't been run yet).
- `reranker.py`: `score(query, docs) -> list[float]`, same lazy-session
  pattern, tokenizes `(query, doc)` pairs, returns flattened logits.
- Patched (per Gemini side-review) with double-checked locking
  (`threading.Lock`) around lazy `_session`/`_tokenizer` init in both
  `embedder.py` and `reranker.py` — needed because spec §11.4 mandates
  `ThreadPoolExecutor` for batch eval, so concurrent first-callers could
  otherwise race and redundantly load the ONNX model multiple times.
- A follow-up Gemini review claimed (a) `export.py` was missing
  `tokenizer.save_pretrained()` and (b) `reranker.py`'s inner lock check
  used `and` instead of `or` — BOTH CLAIMS WERE FALSE when checked
  against the actual files (tokenizer save was already present; both
  files already used `or`). Lesson: always re-read the actual current
  file content before trusting an external review's claims about it —
  don't apply a fix for a bug that verification shows doesn't exist.
  The review's *general* suggestion (build session+tokenizer into local
  vars, assign to globals only after both succeed, so a mid-init
  exception never leaves a half-initialized global pair) WAS valid and
  was applied to both files.
- Third Gemini review round: correctly caught that `embedder.py.embed()`
  was missing the empty-input guard that `reranker.py.score()` already
  had, and correctly flagged that the shared singleton `InferenceSession`
  defaults to fanning out across all CPU cores per `.run()` call, which
  thrashes under concurrent `ThreadPoolExecutor` callers. Both fixed in
  both files: `SessionOptions().intra_op_num_threads = inter_op_num_threads
  = 1` at session construction (applied to reranker.py too, even though
  Gemini's patch only showed embedder.py — same shared-session pattern,
  same fix needed), and `embed([])` now returns a properly-shaped
  `np.empty((0, EMBEDDING_DIM))` rather than Gemini's suggested 1-D
  `np.array([])` (which would break shape-`(n, dim)` assumptions
  downstream).
- Fourth Gemini review (optional optimization, accepted): replaced
  hardcoded ONNX output names (`"last_hidden_state"`, `"logits"`) with
  `session.get_outputs()[0].name` dynamic resolution in both
  `embedder.py` and `reranker.py` — Gemini's patch only covered
  embedder.py; extended the identical fix to reranker.py for
  consistency since the same toolchain-portability rationale applies.
- IMPORTANT PyPI compatibility finding (verified via PyPI JSON API):
  `optimum` 2.x split ONNX export/inference into a separate `optimum-onnx`
  package. Latest `optimum-onnx` (0.1.0) requires `optimum~=2.1.0` (NOT the
  newest `optimum==2.3.0`) and `transformers<4.58.0,>=4.36`. Import path is
  unchanged: `from optimum.onnxruntime import ORTModelForXXX` still works
  (optimum-onnx provides the `optimum.onnxruntime` namespace). Pinned
  accordingly: `optimum[onnxruntime]==2.1.0`, `transformers==4.57.6`,
  `onnxruntime==1.29.0` (requires Python>=3.11 — fine, matches spec),
  `numpy==2.3.5` (requires Python>=3.11). All verified to actually exist
  and be non-yanked on PyPI as of 2026-08-24.

## src/llm/ (new package, spec §6)
- `__init__.py`, `base.py`, `openai_client.py`, `gemini_client.py`, `factory.py`.
- `base.py`: `LLMResponse` dataclass (text, prompt_tokens, completion_tokens,
  total_tokens, latency_seconds, cost_usd, model) + abstract `LLMClient`
  with `complete()` and `structured()`. Deliberately reused `LLMResponse`
  as `structured()`'s second return value instead of inventing a separate
  `Usage` type (spec mentions "Usage" but never defines it distinctly).
- `openai_client.py`: `OpenAIClient` via `openai.OpenAI().chat.completions.create()`
  (NOT the newer `.responses.create()` — Chat Completions is simpler and
  still "supported indefinitely" per the SDK's own README). Structured
  output implemented via `response_format={"type": "json_object"}` +
  the target Pydantic schema's `model_json_schema()` embedded in the
  system prompt, then `schema.model_validate_json(...)` — chosen over
  the `.parse()` convenience helper because its exact availability/
  behavior on openai==3.3.1 (a major version with the new Responses API
  as primary) could not be confirmed from the README.
- `gemini_client.py`: `GeminiClient` via `google.genai.Client().models.generate_content()`.
  Structured output uses the CONFIRMED-from-docs pattern:
  `types.GenerateContentConfig(response_mime_type='application/json',
  response_json_schema=schema.model_json_schema())`, then
  `schema.model_validate_json(response.text)`. Usage read from
  `response.usage_metadata.{prompt_token_count,candidates_token_count,total_token_count}`.
- `factory.py`: `get_llm(provider: str | None = None) -> LLMClient`,
  defaults to `config.DEFAULT_LLM_PROVIDER`, raises `ValueError` on
  unknown provider.
- Added pins (verified via PyPI JSON API, all exist/non-yanked as of
  2026-08-24): `openai==3.3.1` (requires Python>=3.10), `google-genai==2.19.0`
  (requires Python>=3.10), `pydantic==2.13.4` (requires Python>=3.9,
  satisfies both openai's `<3,>=1.10.13` and google-genai's
  `<3.0.0,>=2.12.5` constraints).
- Gemini review round (llm module): claims were VERIFIED TRUE this time
  (no retry logic, unused `logger`, OpenAI `structured()` parsed raw
  JSON with no markdown-fence handling) — applied fixes:
  - Added `tenacity==9.1.2` to requirements.txt.
  - `openai_client.py`: `@_retry_openai` (tenacity, retries
    `openai.RateLimitError/APIConnectionError/InternalServerError`,
    `APITimeoutError` covered via subclassing `APIConnectionError`)
    decorating both `complete()` and `structured()`. Added
    `_strip_markdown_fence()` helper (safer than Gemini's proposed
    blind first/last-line strip — only strips if a real ``` fence
    wraps the text) + `logger.error` on parse failure before re-raise.
  - `gemini_client.py`: Gemini's own patch suggested
    `google.api_core.exceptions` for retry, which is WRONG — that's
    the older Vertex/google-cloud-aiplatform SDK. The `google-genai`
    package (confirmed via its `errors.py` source on GitHub) raises
    `google.genai.errors.ClientError` (4xx)/`ServerError` (5xx), both
    exposing a `.code` int. Used a `retry_if_exception` predicate
    (`_is_retryable_gemini_error`) retrying on `ServerError` always and
    `ClientError` only when `code == 429`, since blindly retrying all
    4xx (e.g. 400 bad request) would be wrong. Decorated `complete()`/
    `structured()`; added matching `logger.error` on parse failure.
  - Lesson: always verify an external review's exact exception-class
    claims against the actual SDK source (fetch the real errors module)
    rather than trusting the reviewer's suggested import path,
    especially for fast-moving/rebranded SDKs like google-genai.
- Own follow-up self-review (no external reviewer) of the whole `src/llm/`
  module against SPEC.MD §6 + config.py, confirmed clean (factory
  default-provider fallback, base.py abstract contract, LLMResponse
  field parity, structured() return order) — found and fixed two small
  remaining gaps:
  - `tenacity` pin was `9.1.2`; PyPI JSON API showed `9.1.4` as latest
    non-yanked (both require Python>=3.10) — bumped for consistency
    with this repo's "pin latest verified" convention.
  - Gemini's original review flagged missing-API-key failures as "not
    cleanly logged" but no patch for it was ever applied. Added
    `logger.warning(...)` in both `OpenAIClient.__init__` and
    `GeminiClient.__init__` when no key resolves from the constructor
    arg or env vars, still followed by the SDK's own fail-fast
    exception (behavior unchanged, just now logged before it happens).

## src/retrieval/ (new package, spec §9)
- `__init__.py` (empty), `query_rewriter.py`, `hybrid_search.py`,
  `reranker_stage.py`, `pipeline.py`.
- No `Document` type existed anywhere before this; defined it in
  `hybrid_search.py` (the file that produces the first candidates) as a
  **frozen** dataclass: `id, component_type, manufacturer_name,
  part_number, search_text, score` (score defaults 0.0). Frozen
  specifically for thread-safety — stage transitions build a new
  instance via `dataclasses.replace(doc, score=...)` instead of
  mutating, so a `Document` can be safely handed across
  `ThreadPoolExecutor` worker threads. Imported from `hybrid_search`
  by both `reranker_stage.py` and `pipeline.py` rather than duplicated.
- `query_rewriter.py`: `rewrite_query(user_query, provider=None) -> str`
  Stage 0. Calls `src.llm.factory.get_llm(provider).complete()` with a
  system prompt instructing acronym/constraint expansion (RoHS,
  fast-switching, etc.). Falls back to the raw query (with a
  `logger.warning`) if the LLM returns empty text. No shared state —
  `get_llm()` builds a fresh client per call — so trivially thread-safe.
- `hybrid_search.py`: Stage 1. `lexical_search()`/`vector_search()` each
  open their own `src.db.knowledge_store.connect()` connection (no
  connection reuse/pooling — deliberate, keeps each call
  independently thread-safe under concurrent `ThreadPoolExecutor` use
  per spec §11.4) and return `Document`s with `score` min-max
  normalized to `[0,1]` (`_minmax_normalize`; all-equal-scores edge
  case maps every score to `1.0`).
  - Lexical: queries `master_fts` directly with the FTS5
    **column-filter MATCH syntax** `WHERE search_text MATCH ?` (bare
    column name as MATCH LHS — confirmed via the official FTS5 docs;
    deliberately did NOT join `master_fts` to `master_table` in the
    same query, since column-filter semantics when a table name is
    qualified with `.` are ambiguous/untested — fetch full rows
    separately via `_fetch_documents()` instead). Query text is passed
    through `_to_fts_match_query()`, which tokenizes with `\w+` and
    OR-joins each token in double quotes — avoids FTS5 syntax errors
    from reserved characters (`-`, `"`, `:`, etc.) in free-form
    rewritten-query text. `bm25()` is "lower is better" — negated
    before min-max normalizing so higher score == more relevant
    everywhere in this module.
  - Vector: embeds the query via `src.models_onnx.embedder.embed()`,
    serializes with `sqlite_vec.serialize_float32()`, queries
    `master_vec` with `WHERE search_vector MATCH ? AND k = {top_k}`
    (`k` inlined as a literal int, not a bound parameter — vec0's
    query planner needs `k` as a literal; safe here since `top_k` is
    always our own `int`, never raw user input). `master_vec` was
    created (in `knowledge_store.py`) WITHOUT `distance_metric=cosine`,
    so it returns **L2** distance by default (confirmed via sqlite-vec
    docs: `vec_distance_L2` returns true, unsquared L2). Since
    `embedder.embed()` L2-normalizes every stored/query vector, this
    converts cleanly to cosine similarity via
    `cos_sim = 1 - (l2_distance ** 2) / 2` before normalizing.
  - `fuse_weighted(vector_scores, keyword_scores, alpha=ACTIVE_ALPHA)`:
    the mandatory `alpha * vector + (1-alpha) * keyword` formula;
    missing ids in either dict default to a `0.0` contribution.
  - `fuse_rrf(ranked_id_lists, k=RRF_K)`: generalized to accept any
    number of ranked id lists (not hardcoded to exactly 2), each
    contributing `1/(k+rank)`.
  - `hybrid_search(rewritten_query, top_k=TOP_K, alpha=None,
    use_rrf=False, rrf_k=RRF_K)`: single public entrypoint switching
    between the two fusion strategies via `use_rrf`, rather than two
    near-duplicate functions — kept RRF as an opt-in alternate per the
    task, with weighted fusion (using `config.ACTIVE_ALPHA`) as the
    default, matching production's `ACTIVE_RETRIEVAL_APPROACH`.
- `reranker_stage.py`: Stage 2. `rerank(query, candidates,
  final_n=FINAL_N)` scores every candidate's `search_text` in one
  batched call to `src.models_onnx.reranker.score()`, rebuilds each
  `Document` via `dataclasses.replace` (never mutates the input list),
  sorts descending, truncates to `final_n`.
- `pipeline.py`: public `retrieve(user_query) -> list[Document]`,
  strictly Stage 0 → 1 → 2 (`rewrite_query` → `hybrid_search` →
  `rerank`), with `logger.info` after each stage. No module-level
  state anywhere in the package.
- Verified FTS5 column-filter MATCH syntax (`col MATCH 'query'` as an
  alternative to `tbl MATCH 'query'`) and sqlite-vec's default L2
  distance metric / `vec_distance_L2` semantics directly from the
  official SQLite FTS5 docs and the sqlite-vec docs site before
  writing the SQL, rather than guessing — both confirmed the design
  above is correct.
- Runtime smoke-testing for this package was skipped (by user
  choice) rather than spinning up the usual temp-venv `-c` check —
  static analysis (`get_errors`) was clean, but the SQL query shapes
  in `hybrid_search.py` have NOT been executed against a real/in-memory
  DB yet. Worth an actual smoke test (e.g. `init_db(':memory:')` +
  a couple of inserted rows + monkeypatched `embed()`) before or during
  `src/evaluation/` work, since that's the first consumer that will
  actually exercise these queries end-to-end.
- Gemini review round 1 (retrieval module): both claims verified TRUE
  — `rewrite_query()` had no try/except around the LLM call (Stage 0
  outage would crash the whole pipeline), and `_to_fts_match_query()`
  returned literal `'""'` for symbol-only input (empty FTS5 MATCH
  string risks a syntax error). Fixed: `rewrite_query()` now wraps the
  LLM call in `try/except Exception` and falls back to the raw query
  (logged via `logger.warning(..., exc_info=True)`); `_to_fts_match_query()`
  now returns `None` for no-token input and `lexical_search()`
  short-circuits to `[]` on `None` instead of duplicating the
  tokenization check inline (kept the single helper as one source of
  truth rather than copy-pasting Gemini's inline patch).
- Own follow-up self-review (no external reviewer) of the whole
  `src/retrieval/` package against `SPEC.MD` §9 + §4.2/§11.3 + its
  actual callers in `src/db`, `src/models_onnx`, `src/llm`: found and
  fixed one real integration gap — `pipeline.retrieve()` always ran
  hybrid_search + cross-encoder rerank unconditionally, completely
  ignoring `config.ACTIVE_RETRIEVAL_APPROACH`. But `config.py`'s own
  comment ("the production retrieval pipeline reads these two values
  at call time") and spec §4.2 ("Production RAG reads these values")
  explicitly require `pipeline.py` to branch on it, since
  `evaluate_retrieval.py` (§11.3) is meant to overwrite that constant
  with the winning approach and have production pick it up with zero
  code changes. Fixed: `retrieve()` now branches on
  `ACTIVE_RETRIEVAL_APPROACH` — `APPROACH_LEXICAL`/`APPROACH_VECTOR` call
  `lexical_search()`/`vector_search()` directly (top_k=`FINAL_N`, no
  rerank stage), `APPROACH_HYBRID` runs `hybrid_search()` truncated to
  `FINAL_N` (no rerank), and `APPROACH_HYBRID_RERANK` (default) plus any
  unrecognized value (logged as a `logger.warning`) run the full
  hybrid+rerank flow. `ACTIVE_ALPHA` did NOT need an equivalent fix —
  `hybrid_search()` already reads it as a top-level import in
  `hybrid_search.py`, and per-call `alpha`/`rrf_k` overrides already
  exist for evaluation's parameter-sweep use case (Approach 4), so
  sweeps never need to mutate the global config at runtime.
  Verified no other module calls `pipeline.retrieve()` yet (`src/rag/`
  and `src/evaluation/` don't exist yet), so this was safe to change
  with no downstream impact.
- All four `src/retrieval/` files double-checked line-by-line against
  their actual dependencies' real signatures (not assumed): confirmed
  `embed(texts: list[str]) -> np.ndarray` and `score(query, docs) ->
  list[float]` call shapes match exactly, and that `vector_search()`'s
  `embed([query_text])[0].tolist()` → `sqlite_vec.serialize_float32()`
  pattern is identical to the one already used in
  `src/ingestion/resources.py`/`pipeline.py` for writing vectors —
  no serialization-format mismatch between ingestion and retrieval.

## Cross-module static integration review (after src/retrieval/ was done)
Reviewed all 6 packages built so far (`config.py`, `db/`, `ingestion/`,
`models_onnx/`, `llm/`, `retrieval/`) together in one pass, not just
each new module against its immediate dependencies as it was built.
- **CRITICAL BUG FOUND & FIXED:** `src/ingestion/pdf_extractor.py`'s
  `_extract_part_number()` had a real Python syntax error — mixed
  tabs/spaces indentation plus a stray dead comment line (looked like
  a manual edit applying a "Gemini code review" suggestion directly in
  the editor, outside my own edit tools, that broke indentation while
  removing the old `lines[:10]` cap). This would have raised a
  `TabError`/`IndentationError` the instant anything imported
  `src.ingestion.pdf_extractor` (i.e. `make ingest` would have crashed
  immediately). Fixed: restored consistent tab indentation, completed
  the intended change (scan every line, not just the first 10), and
  removed the dead commented-out line.
- **IMPORTANT TOOLING LESSON:** the general `get_errors` tool reported
  **no errors** on this exact file even with the syntax error present.
  Only the dedicated `mcp_pylance_mcp_s_pylanceFileSyntaxErrors` MCP
  tool (needs `fileUri` as `file:///...` and a `workspaceRoot`) actually
  caught it (`TabError`-equivalent diagnostics). **Going forward, run
  `pylanceFileSyntaxErrors` on every file in a review/smoke-test pass —
  don't rely on `get_errors` alone for syntax validation**, especially
  for any file that might have been hand-edited outside my own tools
  between sessions.
- Everything else checked out clean: config.py exposes every constant
  every other module imports; `master_table`/`master_fts`/`master_vec`
  schema in `knowledge_store.py` matches exactly what `ingestion/`
  writes and `retrieval/` queries; `pdf_extractor.py`'s `ExtractedFields`
  keys match what `resources.py` reads; `resources.py`'s 5 yielded
  fields match `ingestion/pipeline.py`'s INSERT column list/order;
  `embedder.embed()`/`reranker.score()` call shapes match every caller
  in both `ingestion/` and `retrieval/`, and the vector-serialization
  pattern (`embed(...)[0].tolist()` → `sqlite_vec.serialize_float32()`)
  is identical at ingestion-time and query-time; `llm/base.py`'s
  abstract `LLMClient` contract is implemented identically by both
  `openai_client.py` and `gemini_client.py`; `export.py` writes ONNX
  models to the exact same `config.EMBEDDING_MODEL_DIR`/
  `RERANKER_MODEL_DIR` paths that `embedder.py`/`reranker.py` load from.
- Lesson reinforced: this bug could only be found by actually reading
  file contents / running a real syntax checker — it would NOT have
  been caught by matching signatures or re-reading my own memory notes,
  since the file was altered outside of my own tool-call history. Worth
  periodically re-reading (not just trusting past notes about) files
  that a human might edit directly in the editor between sessions.

## src/db/monitoring_store.py (spec §5.3, §12.1)
- Sibling of `knowledge_store.py`, same connection-management pattern:
  `get_connection(db_path=MONITORING_DB)` (row_factory, foreign_keys ON,
  WAL) / `connect()` contextmanager / `init_db()`. No sqlite-vec
  extension needed here (no vector columns).
- Schema: `conversations` (id TEXT/UUID PK, query, rewritten_query
  nullable, answer, prompt, model, prompt_tokens/completion_tokens/
  total_tokens, response_time, cost, timestamp TEXT UTC ISO-8601) +
  `feedback` (id INTEGER PK, conversation_id TEXT FK →
  conversations.id ON DELETE CASCADE, source "user"/"judge", score
  nullable INTEGER, label nullable TEXT, explanation nullable TEXT,
  timestamp). Index on `feedback.conversation_id`.
- Public API: `insert_conversation(...) -> str` and
  `insert_feedback(...) -> int`, both generating the id/UUID and
  timezone-aware UTC timestamp internally (callers just pass data) and
  each opening+closing its own connection via `connect()` — same
  independently-thread-safe-per-call pattern as
  `retrieval/hybrid_search.py`, safe under concurrent
  `ThreadPoolExecutor` callers (`rag/generator.py`, `rag/judge.py`,
  `qa_panel.py` will all call these). `insert_feedback()` raises
  `ValueError` if `source` isn't exactly `"user"`/`"judge"` (boundary
  validation, per spec §12.2).
- Built from two competing hand-written prompts (mine for Claude vs.
  Gemini's) — compared against spec §5.3 first: Gemini's version was
  missing `rewritten_query` and `model` columns and the judge's
  `label`/`explanation` feedback columns, so went with the
  spec-complete one (mine) rather than merging both.
- No new `requirements.txt` entries — only stdlib (`sqlite3`, `uuid`,
  `datetime`) used.
- Smoke-tested against a real temp-file SQLite DB (not `:memory:` —
  each `:memory:` connection is a separate empty DB, so multi-call
  in-memory testing across `init_db()`/`insert_*()` doesn't share state;
  this is expected sqlite behavior, not a module bug, and matches how
  production will actually use a real file path): schema init, a
  conversation insert, both a "user" and a "judge" feedback insert
  (FK-linked, correct nullable columns), and the `source` ValueError
  guard all verified working end-to-end via a throwaway venv
  (`python-dotenv` only dependency needed to import `src.config`).
- `pylanceFileSyntaxErrors` + `get_errors` both clean; grepped for
  debug leftovers (none) and confirmed no other module references
  `monitoring_store`/`MONITORING_DB` yet (`src/rag/` doesn't exist yet
  — expected, this module has no consumers wired up yet).
- Gemini review round 1 (monitoring_store): overall verdict APPROVED,
  one real finding accepted — `insert_feedback()`'s
  `assert feedback_id is not None` is stripped when Python runs with
  `-O`/`-OO`, silently defeating the guard. Replaced with an explicit
  `if feedback_id is None: raise RuntimeError(...)` (exact patch
  Gemini proposed, applied as-is after re-reading the actual file to
  confirm the assert was really there). No other findings from this
  review were actionable — rest was confirmation of already-correct
  behavior (WAL/FK pragmas, schema, `__all__`, thread-safety pattern).
- Own follow-up self-review (no external reviewer), found and fixed
  three real gaps:
  1. **Concurrency bug risk:** `get_connection()` set `WAL` journal mode
     but never set `PRAGMA busy_timeout`. WAL still serializes writers,
     so with the default 0 busy_timeout, a second concurrent writer
     (e.g. `ThreadPoolExecutor` evaluation calling `insert_feedback()`/
     `insert_conversation()` in parallel — exactly the concurrency
     pattern the module was designed for) would get an immediate
     `sqlite3.OperationalError: database is locked` instead of
     waiting a few ms for the first short insert+commit to finish.
     Added `conn.execute("PRAGMA busy_timeout = 5000;")`. **Same gap
     likely exists in `knowledge_store.py`'s `get_connection()` too —
     not fixed there yet (out of scope for this session), worth
     revisiting** since it has the identical WAL-without-busy_timeout
     pattern. (Note: this WAS later fixed — see cross-module review #4
     below.)
  2. **Defense-in-depth:** added `CHECK (source IN ('user', 'judge'))`
     directly on the `feedback.source` column, so the constraint holds
     even if some future code path inserts via raw SQL and bypasses
     `insert_feedback()`'s Python-level `ValueError` guard. Verified
     both layers independently (Python `ValueError` for the public API,
     DB-level `sqlite3.IntegrityError` for a raw bypass insert).
  3. **Doc accuracy:** module docstring said aggregation/reporting
     queries for the dashboard live in `src/monitoring/` (an
     invented/wrong path) — corrected to the actual planned location
     per `SPEC.MD`'s file tree, `src/app/dashboard.py`.
  - All three re-verified via a fresh throwaway venv + temp-file DB
    smoke test (inserts still succeed, Python `ValueError` still fires
    first, DB `CHECK` constraint independently fires on a raw bypass
    insert, `PRAGMA busy_timeout` reads back as `5000` on a fresh
    connection). `pylanceFileSyntaxErrors` + `get_errors` clean after
    the edits.

## Cross-module static integration review #2 (after src/db/monitoring_store.py)
Re-read all 22 `src/` files in full (not relying on past notes) and ran
`pylanceFileSyntaxErrors` individually on every one, plus `get_errors`
on the whole `src/` tree — **all clean, zero errors, no new bugs found**
(the two review rounds earlier in this same session already caught and
fixed the real issues in `monitoring_store.py`: the `assert`
under `-O` and the missing `busy_timeout`/CHECK constraint/docstring
gaps). Cross-module wiring, DB schema/field-name consistency end-to-end,
`requirements.txt` coverage of every third-party import, and all 6
`__init__.py` files (empty, as intended) all verified clean. Grepped for
`print(`/`TODO`/`FIXME`/`pdb`/`breakpoint` across all of `src/`: one hit,
`print(load_info)` in `ingestion/pipeline.py`'s `run()` — judged
intentional (CLI entrypoint stdout feedback for `make ingest`, alongside
the existing `logger.info`), not a leftover.
- **Forward-compatibility note for `src/rag/generator.py` (not a bug
  yet — no caller exists today):** `llm/base.py`'s `LLMResponse` uses
  field names `cost_usd`/`latency_seconds`; `monitoring_store.py`'s
  `insert_conversation()` uses `cost`/`response_time`. Whoever builds
  `rag/generator.py` will need to map these across the boundary
  explicitly (e.g. `insert_conversation(..., cost=llm_response.cost_usd,
  response_time=llm_response.latency_seconds, ...)`) — no code change
  made now since renaming either side without seeing the actual
  generator.py design would be speculative/over-engineering.
  (Resolved — see `src/rag/generator.py` entry below.)

## src/retrieval/pipeline.py — signature change for src/rag/generator.py
- `retrieve(user_query) -> list[Document]` changed to
  `retrieve(user_query) -> RetrievalResult` (new frozen dataclass:
  `rewritten_query: str`, `documents: list[Document]`), defined in
  `pipeline.py` itself (not `hybrid_search.py`, since it wraps Stage 0's
  output, not a Stage-1 concept) and added to `__all__`. Reason:
  `rag/generator.py` needs the Stage-0 rewritten query to populate
  `monitoring_store.insert_conversation()`'s `rewritten_query` column,
  and `retrieve()` previously discarded it after Stage 0. Verified (via
  grep) there were zero callers of `retrieve()` anywhere in `src/` before
  this change, so it was safe to change the signature directly instead
  of adding a second function. `hybrid_search.py`/`reranker_stage.py`
  untouched — only `pipeline.py`'s final return statement changed.

## src/rag/ (new package, spec §10.1, first module in this package)
- `__init__.py` (empty), `generator.py`.
- `generator.py`: single public function
  `generate_answer(user_query, provider=None) -> GeneratedAnswer`.
  Orchestrates `retrieval.pipeline.retrieve()` -> prompt construction ->
  `llm.factory.get_llm(provider).complete()` -> `db.monitoring_store.
  insert_conversation()`, mirroring `retrieval/pipeline.py`'s
  orchestration style (no module-level state, `logger.info` after each
  stage, `provider: str | None = None` passthrough matching
  `query_rewriter.rewrite_query()`).
- `GeneratedAnswer` dataclass (not a raw dict): `conversation_id, answer,
  prompt, model, prompt_tokens, completion_tokens, total_tokens,
  latency_seconds, cost_usd`. Field names `latency_seconds`/`cost_usd`
  deliberately kept matching `llm.base.LLMResponse` (not
  `monitoring_store`'s `response_time`/`cost`) since this dataclass is
  generator.py's own public return type, not the DB layer.
- **Resolved the known `cost_usd`/`latency_seconds` vs `cost`/
  `response_time` naming gap** (flagged in the cross-module review after
  `monitoring_store.py` was built): `generate_answer()` explicitly maps
  `response.latency_seconds -> response_time` and `response.cost_usd ->
  cost` at the `insert_conversation()` call site. No rename on either
  side, per that earlier note.
- System prompt (`_SYSTEM_PROMPT`) instructs the LLM to answer only from
  the provided context, cite `part_number` per claim, and say "I don't
  know" if the context is insufficient — same terse/technical tone as
  `query_rewriter.py`'s system prompt. `_format_context()` returns an
  explicit `"No matching MOSFET datasheet content was retrieved for
  this query."` notice (not an empty string) when `documents` is empty,
  so the LLM never receives a silently-empty context block.
- The user-turn prompt sent to `llm.complete(prompt, system=_SYSTEM_PROMPT)`
  is just `Context:\n...\n\nQuestion: ...` (no duplicated system text).
  Separately, `full_prompt = f"{_SYSTEM_PROMPT}\n\n{prompt}"` is built
  only for storage (`insert_conversation`'s `prompt` column and
  `GeneratedAnswer.prompt`), so the DB/return value records the complete
  text actually sent to the LLM without sending the system instructions
  to the model twice (would have wasted tokens/cost).
- Thread-safe by construction: no module-level mutable state; every
  call opens its own `LLMClient`/DB connection via the callees it wires
  together (all already independently thread-safe per their own memory
  entries).
- No new `requirements.txt` entries — only stdlib (`dataclasses`,
  `logging`) plus existing internal `src.*` imports.
- Runtime smoke-tested (not just static checks) in a fresh throwaway
  venv with the *full* `requirements.txt` installed (needed because
  importing `generator.py` transitively imports `models_onnx.embedder`
  (numpy/onnxruntime/transformers) and both LLM clients
  (openai/google-genai/tenacity/pydantic) via `retrieval.pipeline` ->
  `retrieval.hybrid_search`/`query_rewriter` -> `llm.factory`). Monkey-
  patched `generator.retrieve` and `generator.get_llm` (module-level
  rebinding, since both are imported via `from ... import` into
  `generator.py`) plus wrapped `insert_conversation` to target a
  temp-file monitoring DB. Verified: a real `conversations` row is
  written with correct `query`/`rewritten_query`/`model`/token counts/
  `response_time`/`cost`/`timestamp`, `GeneratedAnswer` fields match the
  fake `LLMResponse`, and the zero-documents case produces the
  no-context notice in the prompt instead of crashing or embedding an
  empty context block. All asserts passed.
- `pylanceFileSyntaxErrors` clean on `generator.py`, `__init__.py`, and
  the edited `retrieval/pipeline.py`; `get_errors` clean on all three.
  No other `src/` module references `rag.generator`/`RetrievalResult`
  yet other than `pipeline.py` itself defining it — expected, `rag/
  judge.py` and `app/qa_panel.py` (future consumers) don't exist yet.

## src/rag/generator.py — Gemini review round 1
- Claim verified TRUE (re-read the actual file before trusting it, per
  standing lesson): `generate_answer()` had no `try/except` around
  `llm.complete()`, so a provider outage/rate-limit/timeout would crash
  the whole call **and** skip `insert_conversation()` entirely, losing
  monitoring visibility into the failure.
- Applied a refined version of Gemini's patch (not verbatim): wrap only
  the `llm.complete()` call in `try/except Exception`, `logger.error(...,
  exc_info=True)`, then build a fallback `LLMResponse` (imported from
  `src.llm.base`, added as a top-level import) with a user-facing
  "generation service unavailable" message and all-zero token/cost/
  latency fields. Execution still falls through to the normal
  `insert_conversation()`/`GeneratedAnswer` construction unchanged, so
  the failure IS captured in monitoring instead of being silently lost.
- Deviations from Gemini's exact proposed patch: (1) moved the
  `LLMResponse` import to module level instead of inside the `except`
  block (matches this repo's no-inline-import convention); (2) used a
  distinct `model="generation-failed"` sentinel constant instead of
  `provider or "unknown-failed"` — makes failed rows unambiguously
  filterable/excludable in future dashboard aggregations (`src/app/
  dashboard.py`) without risking collision with a real provider name;
  (3) kept the fallback message/model as module-level constants
  (`_GENERATION_FAILURE_MESSAGE`, `_GENERATION_FAILURE_MODEL`) rather
  than inline literals, consistent with `_NO_CONTEXT_MESSAGE`'s existing
  pattern in the same file.
- Runtime smoke-tested (not just static checks) in a fresh temp venv
  with full `requirements.txt`: happy path unaffected (real `LLMResponse`
  still flows through unchanged), and a simulated `RuntimeError` from a
  fake failing `LLMClient` confirmed `generate_answer()` (a) does not
  raise, (b) logs the error, (c) still returns a `GeneratedAnswer` with
  the fallback text/`model="generation-failed"`, and (d) still writes a
  real `conversations` row with the same sentinel values. All asserts
  passed. `get_errors` + `pylanceFileSyntaxErrors` clean after the edit.
- No other findings from this review round were actionable — the rest
  of Gemini's "APPROVED WITH MINOR ACTION REQUIRED" verdict was
  confirmation of already-correct behavior (it explicitly praised the
  self-caught double-system-prompt fix from the implementation session).

## src/rag/generator.py — self-review round (before a second Gemini pass)
- Requested by the user explicitly to catch bugs proactively before
  sending the file back to Gemini again.
- **Found and fixed a real gap in the Gemini-round-1 patch itself:**
  the `try/except` only wrapped `llm.complete()`, not `llm = get_llm(provider)`.
  But `get_llm()` can itself raise — `ValueError` for an unknown
  `provider` string, or (per the earlier `src/llm/` review notes) the
  underlying `openai`/`google-genai` SDK client constructor can fail
  fast on a missing API key. Either would have crashed `generate_answer()`
  **before** the try block, reproducing the exact "no telemetry logged"
  failure mode Gemini's round-1 review had just fixed for the
  `.complete()` call specifically. Fixed by moving `llm = get_llm(provider)`
  inside the same `try` block, and added `provider` to the
  `logger.error(...)` call for debuggability (kept the DB `model` column
  as the fixed `"generation-failed"` sentinel rather than encoding
  `provider` into it, to keep that column's semantics — "model actually
  used" — clean and simply groupable).
- **Deliberately NOT changed** (documented as a scope boundary in the
  function's docstring instead, so a future reviewer doesn't re-flag it
  as an oversight): `retrieve(user_query)` itself is not wrapped in
  `try/except`. Retrieval-layer failures (SQLite/ONNX runtime down)
  indicate an infrastructure-level outage rather than a transient
  provider-side hiccup, so letting them propagate (rather than silently
  degrading to a canned answer) was judged the more correct behavior —
  unlike an LLM outage, swallowing a broken DB/embedder connection could
  mask a serious operational problem.
- Runtime smoke-tested (temp venv, full `requirements.txt`, 3 scenarios
  in one script): happy path unaffected; `llm.complete()` raising still
  degrades gracefully as before; **new** — `get_llm()` itself raising
  (`ValueError` for an unknown provider) now also degrades gracefully
  instead of crashing, and all three scenarios each still persist a
  `conversations` row (verified via `SELECT COUNT(*) = 3`). `get_errors`
  + `pylanceFileSyntaxErrors` clean after the edit.

## Cross-module static integration review #3 (after src/rag/generator.py + self-review + Gemini round 1)
Re-read all 24 `src/` files in full (7 empty `__init__.py` + 17 substantive
modules, including the new `src/rag/` package) and ran
`pylanceFileSyntaxErrors` individually on all 17 substantive files, plus
`get_errors` on the whole `src/` tree — **all clean, zero syntax errors**.
- **Found and fixed one real duplication:** `_cost_usd()` (identical
  `PRICING_PER_1K_TOKENS.get(self.model, ...)` formula) was copy-pasted
  verbatim in both `openai_client.py` and `gemini_client.py`. Consolidated
  into a single concrete method on the `LLMClient` ABC in `base.py`
  (added `model: str` as a documented instance-attribute annotation on
  the ABC, and imported `PRICING_PER_1K_TOKENS` there instead of in each
  subclass); removed the duplicate method + now-unused
  `PRICING_PER_1K_TOKENS` import from both client files. Runtime
  smoke-tested (temp venv with just `python-dotenv openai google-genai
  pydantic tenacity`, no heavy ONNX deps needed since this doesn't touch
  `models_onnx`): both clients' inherited `_cost_usd()` produces
  byte-identical results to the pre-refactor duplicated versions, and
  the unknown-model fallback (`{"prompt": 0.0, "completion": 0.0}`)
  still works. `get_errors` + `pylanceFileSyntaxErrors` clean on all 3
  touched files after the edit.
- **Known, deliberately-NOT-touched duplication:** `models_onnx/embedder.py`
  and `models_onnx/reranker.py` still share near-identical
  `_model_path()`/`_get_session()` double-checked-locking boilerplate
  (each with its own independent module-level `_session`/`_tokenizer`
  cache). Left as-is — per this file's own history (4 prior Gemini
  review rounds, see the `src/models_onnx/` entry above), every past fix
  to this pattern was deliberately applied identically to *both* files
  rather than consolidated into a shared helper, so treating this as
  established precedent rather than re-litigating it as a new finding.
  Consolidating now would also be a materially bigger/riskier refactor
  than the `_cost_usd` case (two independent lazy-init global caches,
  not a single pure function), so it was judged out of scope for this
  review pass.
- **Cross-module wiring:** every constant `src/rag/generator.py` and
  every other module imports from `config.py` actually exists (no
  missing constants). `LLMResponse` field names identical across
  `base.py`/both clients/`generator.py`'s fallback construction.
  `insert_conversation()`'s parameter names match `generator.py`'s call
  site exactly (`response_time`/`cost` mapping intentional, documented).
  `master_table`/`master_fts`/`master_vec` column names identical across
  `knowledge_store.py` (schema), `ingestion/pipeline.py` (INSERT),
  `ingestion/resources.py` (`MasterTableRecord`), and
  `retrieval/hybrid_search.py` (`Document`/queries) — no drift.
  `embed()`/`score()` call shapes match every caller in `ingestion/` and
  `retrieval/`. No import cycle: dependency direction is strictly
  `config -> {db, llm, models_onnx} -> retrieval -> rag`, plus
  `config -> ingestion` (via `db`/`models_onnx`) — verified by listing
  every module's internal imports, no back-edges found.
- **`requirements.txt` audit:** every third-party import across all 17
  substantive files (`dotenv`, `sqlite_vec`, `dlt`, `fitz`, `optimum.*`,
  `transformers`, `onnxruntime`, `numpy`, `openai`, `google.genai`,
  `pydantic`, `tenacity`) is pinned; nothing pinned-but-unused either.
- **`__init__.py` audit:** all 7 (`src/`, `db/`, `ingestion/`, `llm/`,
  `models_onnx/`, `retrieval/`, `rag/`) confirmed empty, as intended.
- **Dead-code grep** (`print(`/`TODO`/`FIXME`/`pdb`/`breakpoint`): one
  hit, the same `print(load_info)` in `ingestion/pipeline.py`'s `run()`
  already judged intentional in cross-module review #2 (CLI stdout
  feedback for `make ingest`) — no new leftovers found anywhere else,
  including the new `src/rag/` package.

## src/rag/judge.py (spec §10.2, second module in src/rag/)
- Single public function `judge_answer(user_query, answer, conversation_id,
  provider=None) -> JudgeResult` (dataclass: `label, explanation, score,
  feedback_id`). Sibling of `generator.py`/`query_rewriter.py`: same
  `provider: str | None = None` passthrough, no module-level mutable
  state, fresh `get_llm(provider)` client per call (thread-safe under
  `evaluate_llm.py`'s future `ThreadPoolExecutor`, spec §11.4).
- `RelevanceVerdict(BaseModel)` (`label: Literal[...]`, `explanation: str`)
  matches spec §10.2 verbatim. This is the ONE caller in the codebase
  using `LLMClient.structured()` instead of `.complete()` — confirmed
  `structured()` returns `(parsed_model, LLMResponse)` by re-reading
  `openai_client.py`'s implementation before writing the call site.
- **Design gap resolved (label -> score mapping, NOT spec-mandated):**
  `RELEVANT=1, PARTLY_RELEVANT=0, NON_RELEVANT=-1` — a judgment call,
  chosen to mirror the user +1/-1 feedback convention (spec §12.2) with
  PARTLY_RELEVANT at the neutral midpoint. Documented as a judgment call
  in the module's own comment, not presented as spec-derived.
- **Design gap resolved (prompt inputs):** judge prompt is `(query,
  answer)` only — no retrieved context `Document`s. Rationale: spec
  §10.2 says the judge evaluates "the relevance of the system's own
  answer" to the query, not groundedness-in-context; and
  `generator.generate_answer()` doesn't return its retrieved documents
  today, so plumbing them through would require widening
  `GeneratedAnswer`'s public contract for a check the spec doesn't ask
  for. Documented in the module docstring so a future reviewer
  understands this was a deliberate choice, not an oversight.
- **Failure handling — deliberately different from `generate_answer()`'s
  fallback-and-persist pattern:** if `get_llm(...).structured()` raises
  (bad provider, missing credentials, rate limit, parse failure), `
  judge_answer()` logs (`logger.error(..., exc_info=True)`) and
  **re-raises** — it does NOT fabricate a verdict or call
  `insert_feedback()`. Rationale given to the user: a made-up relevance
  label would silently corrupt real monitoring data, which is strictly
  worse than a missing feedback row; and under `evaluate_llm.py`'s
  future `ThreadPoolExecutor` batch (spec §11.4), letting the exception
  propagate through the submitted `Future` is the idiomatic way for the
  batch caller to catch/count/skip that one failed item via
  `future.result()`'s own exception propagation, without losing
  visibility into *why* judge coverage is incomplete for that item.
- No new `requirements.txt` entries — only stdlib (`dataclasses`,
  `logging`, `typing.Literal`) plus already-pinned `pydantic` and
  existing internal `src.*` imports.
- Runtime smoke-tested in a throwaway venv (`python-dotenv openai
  google-genai pydantic tenacity` only — no ONNX deps needed, judge.py
  never imports `retrieval`/`models_onnx`). Monkeypatched `judge.get_llm`
  and `judge.insert_feedback` (module-level rebinding, since both are
  imported via `from ... import`) against a real temp-file monitoring
  DB (seeded with one `conversations` row). Verified: (a) happy path
  writes a real `feedback` row with `source="judge"`,
  `score=0`/`label="PARTLY_RELEVANT"`/matching `explanation`, and
  `JudgeResult` mirrors it exactly; (b) a simulated `RuntimeError` from
  `.structured()` propagates out of `judge_answer()` unchanged (no
  fabricated row persisted — feedback count stayed at 1); (c) direct
  `insert_feedback(source="bogus")` still raises `ValueError` (existing
  `monitoring_store.py` guard, exercised through this module's own call
  path). All assertions passed.
- `pylanceFileSyntaxErrors` + `get_errors` both clean. `__init__.py`
  audit: all packages (incl. `src/rag/`) still empty. Dead-code grep
  across all of `src/` still shows only the one already-judged-
  intentional `print(load_info)` in `ingestion/pipeline.py`. No other
  module references `rag.judge`/`JudgeResult`/`RelevanceVerdict` yet
  (`evaluate_llm.py`/`qa_panel.py` don't exist yet) — expected.
- **Self-review round (found and fixed a real gap):** the initial cut
  wrapped only `get_llm(...).structured()` in try/except; the
  `insert_feedback(...)` call right after it had NO error handling at
  all, so a persistence failure (e.g. FK violation if `conversation_id`
  doesn't actually exist, or a lock/timeout) would propagate with zero
  logging — silently losing a verdict that already cost a real LLM
  call. Fixed: `insert_feedback(...)` is now its own try/except that
  logs the verdict (`label`/`score`/`explanation`) plus `exc_info=True`
  before re-raising, so the content isn't lost even when persistence
  itself fails. Docstring's `Raises` section updated to cover both
  failure points. Re-verified via a second throwaway-venv smoke test
  (temp DB with NO matching `conversations` row -> real
  `sqlite3.IntegrityError`, confirmed logged + re-raised + zero feedback
  rows persisted).

## Cross-module static integration review #4 (after src/rag/judge.py + its self-review)
Re-read all 26 `src/` files in full (7 empty `__init__.py` + 19 substantive
modules) and ran `pylanceFileSyntaxErrors` individually on all 19
substantive files, plus `get_errors` on the whole `src/` tree —
**all clean, zero syntax errors**.
- **Found and fixed one real, previously-flagged-but-deferred gap:**
  `src/db/knowledge_store.py`'s `get_connection()` set WAL journal mode
  but never set `PRAGMA busy_timeout` — the exact same gap already
  found and fixed in `monitoring_store.py` two review rounds ago, where
  the note explicitly said "same gap likely exists in
  `knowledge_store.py` too — not fixed there yet". Fixed now: added
  `conn.execute("PRAGMA busy_timeout = 5000;")` right after the WAL
  pragma, identical value/pattern/comment style to
  `monitoring_store.py`. Re-ran `pylanceFileSyntaxErrors` + `get_errors`
  on the file — both clean.
- **Cross-module wiring, re-verified end-to-end (not just spot-checked):**
  every constant every module imports from `config.py` exists;
  `LLMClient` abstract contract (`complete`/`structured`/`_cost_usd`) is
  implemented identically by both `openai_client.py`/`gemini_client.py`
  (no reintroduced duplication); `Document`'s fields are used
  identically and without drift across `hybrid_search.py` (producer),
  `reranker_stage.py`, `retrieval/pipeline.py`, and `rag/generator.py`
  (consumers); `RetrievalResult.rewritten_query`/`.documents` match
  exactly what `generator.py` reads; `insert_conversation()`/
  `insert_feedback()` parameter names match their only two call sites
  (`rag/generator.py`, `rag/judge.py`) exactly; `master_table`/
  `master_fts`/`master_vec` column names remain consistent across
  `knowledge_store.py` (schema), `ingestion/pipeline.py` (INSERT column
  order), `ingestion/resources.py` (`MasterTableRecord` keys), and
  `retrieval/hybrid_search.py` (SELECT/`Document` fields); `embed()`/
  `score()` call shapes match every caller. **No import cycle:**
  dependency direction is still strictly `config -> {db, llm,
  models_onnx} -> retrieval -> rag`, plus `config -> ingestion` (via
  `db`/`models_onnx`) — verified by listing every module's internal
  imports again from scratch.
- **`requirements.txt` audit:** every third-party import across all 19
  substantive files (`dotenv`, `sqlite_vec`, `dlt`, `fitz`, `optimum.*`,
  `transformers`, `onnxruntime`, `numpy`, `openai`, `google.genai`,
  `pydantic`, `tenacity`) is pinned; nothing pinned-but-unused. `judge.py`
  needed no new entries (stdlib + already-pinned `pydantic` only).
- **`__init__.py` audit:** all 7 (`src/`, `db/`, `ingestion/`, `llm/`,
  `models_onnx/`, `retrieval/`, `rag/`) confirmed empty, as intended.
- **Dead-code grep** (`print(`/`TODO`/`FIXME`/`pdb`/`breakpoint`): still
  only the one already-judged-intentional `print(load_info)` in
  `ingestion/pipeline.py`'s `run()` — no new leftovers anywhere,
  including `rag/judge.py`.
- No other new findings — `rag/judge.py`'s own two review rounds
  (initial build + the `insert_feedback` error-handling self-review)
  already caught the only real bugs introduced by that module.

## Reusable prompt: end-of-module review (give this after each new module)
> Do a static cross-module integration review of everything built so far.
> Re-read every file in full (don't rely on past notes about their
> contents) and run a dedicated Python syntax check on each one — use
> the Pylance syntax-checker tool specifically
> (`mcp_pylance_mcp_s_pylanceFileSyntaxErrors`, needs `fileUri` as
> `file:///...` plus `workspaceRoot`), not just the general `get_errors`
> tool, since `get_errors` has been observed to miss real syntax errors
> (e.g. mixed tabs/spaces). Then verify cross-module wiring: every
> constant/function one module imports from another actually exists
> with a matching signature; database schemas, field names, and data
> shapes stay consistent end-to-end across every producer/consumer
> pair; no module silently duplicates or contradicts logic defined
> elsewhere; and there's no import cycle (map the dependency direction
> between packages). Also do these quick housekeeping checks: (a) cross-
> reference every third-party `import` across `src/` against
> `requirements.txt` and flag anything used but unpinned; (b) confirm
> every package's `__init__.py` exists and is empty as intended; (c)
> grep for debug leftovers/dead code (`print(`, `TODO`, `FIXME`, `pdb`,
> `breakpoint`) and judge whether each hit is intentional or a leftover.
> Report any bugs found, fix them, and update repo memory with what was
> found.

## Hygiene lesson: temp-file DB cleanup (found during a workspace hygiene/security check)
- Smoke tests use `tempfile.NamedTemporaryFile(suffix=".db", delete=False).name`
  for a real on-disk SQLite path (deliberate -- `:memory:` doesn't share
  state across connections). But `delete=False` means the file is NEVER
  auto-removed, and past cleanup commands only deleted the throwaway
  venv + test script, not this DB path. Result: orphaned `tmp*.db`
  files/`test_monitoring.db`-containing tmp dirs were found still
  sitting in `%TEMP%` from both the `generator.py` and `judge.py`
  smoke-test sessions, discovered only by an explicit hygiene sweep.
  **Going forward: every smoke-test cleanup command must also
  explicitly delete the `tempfile.NamedTemporaryFile`/`tempfile.mkdtemp`
  path it created**, not just the venv + script.

## src/evaluation/ (spec §11) — pre-build design note, resolved before any code written
- Build order is sequential, not parallel: `generate_ground_truth.py` ->
  `evaluate_retrieval.py` -> `evaluate_llm.py`. Reason: both later
  modules consume `data/ground_truth.csv` from the first; running
  `evaluate_retrieval.py` before `evaluate_llm.py` also means the LLM
  eval's `generate_answer()` calls (via `retrieve()`) reflect the
  already-tuned `config.ACTIVE_RETRIEVAL_APPROACH`/`ACTIVE_ALPHA`
  instead of untuned defaults.
- **Resolved an apparent §11.1/§11.4 schema gap (user-clarified, no code
  change needed elsewhere):** §11.4's "A -> Q -> A'" framework needs a
  source answer `A`, but §11.1's `ground_truth.csv` schema is only
  `question`/`document_id` -- no `answer` column. Confirmed this is NOT
  a gap: `A` **is** the matched `master_table` record's `search_text`
  (the Descriptions+Features+Applications blob already extracted at
  ingestion time), not a value stored redundantly in the CSV.
  `generate_ground_truth.py` generates ~5 `Q`s per record *from* that
  record's `search_text` and writes only `document_id` (=
  `master_table.id`) + `question` to the CSV, exactly per §11.1's
  literal schema. `evaluate_llm.py` resolves `A` at evaluation time via
  a simple join (`SELECT search_text FROM master_table WHERE id = ?`)
  keyed on `document_id` -- single source of truth in `master_table`,
  no duplicated/driftable copy of `A` in the CSV. Do not add an `answer`
  column to `ground_truth.csv` when building `generate_ground_truth.py`.

## src/evaluation/generate_ground_truth.py (spec §11.1, first module in src/evaluation/)
- `__init__.py` (empty), `generate_ground_truth.py`.
- Single public function `generate_ground_truth(provider: str | None = None) -> int`,
  same `provider` passthrough pattern as `rewrite_query()`/`generate_answer()`/
  `judge_answer()`. `Questions(BaseModel)` (`questions: list[str]`) defined
  here verbatim per spec §11.1. `__main__` entrypoint
  (`logging.basicConfig` + call) for `make ground-truth`, matching
  `ingestion/pipeline.py`/`models_onnx/export.py`'s pattern.
- Flow: `src.db.knowledge_store.connect()` -> `SELECT id, search_text FROM
  master_table` (one query, all records) -> for each record, if
  `search_text` empty/missing, `logger.warning` + skip (matches
  `pdf_extractor.py`/`resources.py`'s "one bad record never aborts the
  whole run" philosophy, spec §8.5); else `get_llm(provider).structured(
  search_text, Questions, system=...)` -> one CSV row per returned
  question (`question`, `document_id=master_table.id`). Per-record
  `.structured()` failures are caught (`logger.error(..., exc_info=True)`)
  and skipped, continuing to the next record — deliberately sequential,
  NOT wrapped in `ThreadPoolExecutor` (spec §11.4 only mandates that for
  `evaluate_llm.py`; this runs once offline over the whole table).
- Writes with stdlib `csv` (no `pandas` — 2-column CSV doesn't warrant the
  new dependency), `open(GROUND_TRUTH_CSV, "w", ...)` — full overwrite
  every run, not an append, per spec's "regenerate the ground-truth set"
  intent. No `answer` column — see the pre-build design note above (A =
  `master_table.search_text`, resolved later by `evaluate_llm.py` via a
  join on `document_id`). Trusts whatever count of questions the LLM
  actually returns (spec says "~5", not an "exactly N" hard rule) — no
  padding/truncation.
- No module-level mutable state (thread-safe by construction, even though
  this module isn't expected to run under a `ThreadPoolExecutor`).
- No new `requirements.txt` entries — only stdlib (`csv`, `logging`) plus
  already-pinned `pydantic` and existing internal `src.*` imports.
- Runtime smoke-tested in a throwaway venv (`python-dotenv sqlite-vec
  openai google-genai tenacity pydantic` — `src.llm.factory` eagerly
  imports both `openai_client.py`/`gemini_client.py`, so both SDKs are
  needed just to import `generate_ground_truth.py` even though the test
  stubs `get_llm` itself). Seeded a real temp-file knowledge DB (`init_db()`
  + two `master_table` rows, one with real `search_text`, one with `''`)
  via `monkeypatch.object(gt, "connect"/"GROUND_TRUTH_CSV"/"get_llm", ...)`
  (module-level rebinding, since all three are imported via `from ...
  import`). Verified: the empty-`search_text` row is skipped (logged
  warning, zero rows for it), the real row produces exactly the 3 stubbed
  questions as 3 CSV rows sharing `document_id="1"`, the CSV header is
  exactly `question,document_id`, and the return value (`3`) matches the
  row count written. All assertions passed; temp venv + temp DB/CSV dirs
  deleted afterward (per the temp-file-DB cleanup hygiene lesson below).
- `pylanceFileSyntaxErrors` + `get_errors` clean on both new files.
  Cross-module review: `config.GROUND_TRUTH_CSV`/`DEFAULT_LLM_PROVIDER`
  both already existed and match exactly; `knowledge_store.connect()`/
  `init_db()` signatures match the call sites; `llm.base.LLMClient
  .structured()`'s `(parsed_model, LLMResponse)` return order matches
  usage here (same pattern as `rag/judge.py`, the only other
  `.structured()` caller); no import cycle (`evaluation` depends on
  `config`/`db`/`llm` only — nothing imports `evaluation` yet, expected
  since `evaluate_retrieval.py`/`evaluate_llm.py` don't exist yet). All 8
  `__init__.py` files (incl. new `src/evaluation/`) confirmed empty.
  `requirements.txt` needed no additions. Dead-code grep still shows only
  the one already-judged-intentional `print(load_info)` in
  `ingestion/pipeline.py`.
- No Makefile exists yet in the workspace — `make ground-truth` is a
  spec-described target, not yet wired up; out of scope for this module.
- **Self-review round (user asked for a bug/issue pass after the initial
  build), found and fixed three real gaps:**
  1. **Partial-file corruption risk:** the original cut opened
     `GROUND_TRUTH_CSV` directly in `"w"` mode and wrote rows
     incrementally, so a mid-run crash (LLM outage, disk error,
     interrupt) would leave a truncated-but-valid-looking CSV in place,
     silently corrupting the ground-truth set instead of failing
     cleanly. Fixed: now writes to a `tempfile.mkstemp(dir=<same dir>,
     prefix=".ground_truth_", suffix=".tmp")` file and only
     `os.replace()`s it over the real target after every record has been
     processed; a `try/except BaseException: os.remove(tmp_path); raise`
     wrapper guarantees the temp file is cleaned up (and the original
     left untouched) on any failure, including one from `os.replace`
     itself.
  2. **Blank questions not filtered:** an empty/whitespace-only string
     returned in the LLM's `questions` list was written as a junk CSV
     row. Fixed: `question.strip()` + skip if empty, before writing.
  3. **Minor type-hint drift from convention:** `_fetch_records(conn)`
     was missing the `conn: sqlite3.Connection` type hint that every
     other DB-helper function in this repo uses (e.g.
     `hybrid_search.py`'s `_fetch_documents`), and its return type said
     `str` when `search_text` is actually nullable in the schema. Fixed
     to `conn: sqlite3.Connection` / `list[tuple[int, str | None]]`.
  - Re-verified via a second throwaway-venv smoke test (3 scenarios):
    (a) happy path with a mix of valid/blank questions returns the
    correct non-blank row count and skips blanks; (b) `_fetch_records`
    raising before any write leaves the pre-existing target CSV
    byte-identical and creates zero leftover temp files; (c) `os.replace`
    itself raising (simulated disk-full) still leaves the original file
    untouched and zero leftover temp files, while the `OSError`
    propagates. All assertions passed. `pylanceFileSyntaxErrors` +
    `get_errors` clean after the edits. Temp venv/DB/CSV dirs deleted
    afterward.

## Cross-module static integration review #5 (after src/evaluation/generate_ground_truth.py + its bug-fix review round)
Re-read all 28 `src/` files in full (8 empty `__init__.py` + 20 substantive
modules, incl. the new `src/evaluation/` package) and ran
`pylanceFileSyntaxErrors` individually on all 20 substantive files, plus
`get_errors` on the whole `src/` tree — **all clean, zero syntax errors,
zero diagnostics**.
- **No new bugs found this round** — `generate_ground_truth.py`'s own two
  prior review rounds (initial build + the user-requested bug-review
  pass) already caught the only real issues introduced by that module.
- **Cross-module wiring, re-verified end-to-end from scratch (not spot-
  checked):** every constant every module imports from `config.py`
  exists with the expected type; `LLMClient.structured()`'s
  `(parsed_model, LLMResponse)` return contract is implemented
  identically by `openai_client.py`/`gemini_client.py` and consumed
  identically by its two callers (`rag/judge.py`, `evaluation/
  generate_ground_truth.py`); `master_table` column names/order stay
  consistent across `knowledge_store.py` (schema), `ingestion/
  pipeline.py` (INSERT), `ingestion/resources.py` (`MasterTableRecord`),
  `retrieval/hybrid_search.py` (`Document`/SELECT), and `evaluation/
  generate_ground_truth.py` (`_fetch_records` SELECT); `conversations`/
  `feedback` column names stay consistent across `monitoring_store.py`
  (schema) and its two callers (`rag/generator.py`, `rag/judge.py`,
  incl. the intentional `cost_usd`/`latency_seconds` ->
  `cost`/`response_time` mapping at the `insert_conversation()` call
  site); `embed()`/`score()` call shapes match every caller in
  `ingestion/` and `retrieval/`. **No import cycle:** dependency
  direction is still strictly `config -> {db, llm, models_onnx} ->
  {ingestion, retrieval} -> rag`, plus the new `evaluation` package
  sitting parallel to `rag` (`config -> {db, llm} -> evaluation`, no
  reverse edges) — verified by listing every module's internal imports
  from scratch, not reusing the prior review's map.
- **`requirements.txt` audit:** every third-party import across all 20
  substantive files (`dotenv`, `sqlite_vec`, `dlt`, `fitz`, `optimum.*`,
  `transformers`, `onnxruntime`, `numpy`, `openai`, `google.genai`,
  `pydantic`, `tenacity`) is pinned; nothing pinned-but-unused.
  `generate_ground_truth.py` needed no new entries (stdlib
  `csv`/`os`/`sqlite3`/`tempfile` + already-pinned `pydantic`).
- **`__init__.py` audit:** all 8 (`src/`, `db/`, `evaluation/`,
  `ingestion/`, `llm/`, `models_onnx/`, `rag/`, `retrieval/`) confirmed
  empty (0 bytes), as intended.
- **Dead-code grep** (`print(`/`TODO`/`FIXME`/`pdb`/`breakpoint`): still
  only the one already-judged-intentional `print(load_info)` in
  `ingestion/pipeline.py`'s `run()` — no new leftovers anywhere,
  including the new `src/evaluation/` package.
- **Stylistic-only observation (not a bug, not fixed):**
  `src/ingestion/pdf_extractor.py` is indented with tabs throughout
  (confirmed via a `^\t` grep — consistently tabs, not a tabs/spaces
  *mix*), unlike every other file in `src/` which uses 4-space indents.
  Pylance reports zero syntax errors on it and it runs correctly, so
  this is purely a formatting inconsistency left over from the earlier
  hand-edit-introduced `TabError` incident (see the "Cross-module static
  integration review (after src/retrieval/ was done)" entry above, where
  the mixed-indentation bug was fixed by restoring consistent tabs, not
  by converting to spaces) — reformatting it now would be a pure-style
  change with no functional benefit, so left as-is per this repo's
  "don't change things beyond what's needed" convention. Worth a
  one-line mention if a future formatter/linter (e.g. `black`) is ever
  added to the project, since it would silently rewrite this file's
  whitespace.

## Environment
- `python` is not on PATH on this machine; use `py` (Python launcher).
  `py --version` → 3.13.5 available (spec targets 3.11, but 3.13 works
  fine for syntax/logic smoke-testing).

## Current status as of this file's creation (2026-08-26)
- **Built so far (in order):** `config.py` (paths only) -> `db/knowledge_store.py`
  -> `ingestion/` (pdf_extractor, resources, pipeline) -> `models_onnx/`
  (export, embedder, reranker) -> `llm/` (base, openai_client,
  gemini_client, factory) -> `retrieval/` (query_rewriter, hybrid_search,
  reranker_stage, pipeline) -> `db/monitoring_store.py` -> `rag/generator.py`
  -> `rag/judge.py` -> `evaluation/generate_ground_truth.py`.
- **Not yet built (per SPEC.MD's file tree):** `src/evaluation/evaluate_retrieval.py`
  (§11.3, writes back `ACTIVE_RETRIEVAL_APPROACH`/`ACTIVE_ALPHA` into
  `config.py`), `src/evaluation/evaluate_llm.py` (§11.4, ThreadPoolExecutor
  batch eval), `src/app/qa_panel.py` + `src/app/dashboard.py` (Streamlit UI),
  `Makefile`, `Dockerfile`/`docker-compose.yml`, `.env.example`. `config.py`
  is also still missing model IDs/TOP_K/FINAL_N/ALPHA/RRF_K/
  ACTIVE_RETRIEVAL_APPROACH/ACTIVE_ALPHA/pricing table/DEFAULT_LLM_PROVIDER
  constants that later modules already assume exist (check `config.py`'s
  actual current content at the start of the next session rather than
  trusting this note, per the standing "re-read files, don't just trust
  memory" lesson).
- **Git:** this workspace had NO git repository until this note's own
  session initialized one (`git init` + first commit including this
  file). Before that, there was no version control at all — treat any
  info about "uncommitted changes" from before this point as unverifiable.
- Next planned module per the sequential build order noted above:
  `src/evaluation/evaluate_retrieval.py`.

## src/evaluation/evaluate_retrieval.py (spec.md §11.2/§11.3)
- Single public function `evaluate_retrieval() -> dict`, `__main__` entrypoint
  (`logging.basicConfig` + call) for `make eval-retrieval`. No module-level
  mutable state (all module "constants" are dicts/tuples, never mutated).
- **4 approaches evaluated (14 result rows total):** Approach 1 `lexical_search`
  only; Approach 2 `vector_search` only; Approach 3 `hybrid_search(use_rrf=True)`
  (RRF, no rerank); Approach 4 `hybrid_search(alpha=a)` -> `reranker_stage.rerank`,
  swept over `alpha in [0.0, 0.1, ..., 1.0]` (11 variants). Metrics (Hit Rate@5 /
  MRR) computed over ALL ground-truth rows, cutoff reuses `config.FINAL_N` (5)
  rather than a new hardcoded constant.
- **Deliberate scope decision (documented in the module docstring):** does NOT
  call `query_rewriter.rewrite_query()` — ground-truth questions (§11.1) are
  already well-formed; Stage 0 is a production-pipeline concern orthogonal to
  comparing the retrieval algorithms themselves.
- **Approach 3 = RRF, not weighted fusion** (spec §11.2 allows either) — chosen
  because spec.md §9.2 explicitly says RRF is "used by evaluation Approach 3",
  and to keep Approach 3 meaningfully distinct from Approach 4's weighted-fusion
  sweep.
- **Real integration bug found & fixed while wiring this in (`src/retrieval/pipeline.py`):**
  `retrieve()`'s `APPROACH_HYBRID` branch called `hybrid_search(rewritten_query)`
  with NO `use_rrf=True` — i.e. production's "basic hybrid" (non-rerank) branch
  was actually running **weighted** fusion, contradicting spec §9.2's explicit
  RRF-for-Approach-3 intent and `evaluate_retrieval.py`'s own Approach 3. If
  Approach 3 (RRF) had won an evaluation run and gotten written to
  `ACTIVE_RETRIEVAL_APPROACH`, production would have silently served a
  different (weighted) fusion than the one actually evaluated/selected. Fixed:
  `APPROACH_HYBRID` branch now calls `hybrid_search(rewritten_query, use_rrf=True)`;
  `APPROACH_HYBRID_RERANK` branch (Approach 4, weighted+rerank) was already
  correct and untouched.
- **Winner selection:** highest MRR across all 14 rows, tie-break on Hit Rate,
  via `max(results, key=lambda r: (r["mrr"], r["hit_rate"]))` — Python's `max()`
  keeps the *first* element reached on a tie, so ties resolve in the fixed
  evaluation order (lexical -> vector -> RRF -> alpha sweep ascending).
- **`config.py` rewrite (spec §11.3):** `_replace_config_source()` operates
  line-by-line (`str.splitlines(keepends=True)` + per-line regex matching a
  captured prefix/value/trailing-comment shape), preserving every other line
  (including each target line's own trailing comment and the file's original
  CRLF line endings, confirmed via a byte-count check) untouched. Read/write
  both use `open(..., newline="")` specifically to avoid Python's universal-
  newline translation silently converting config.py's CRLF endings to LF (or
  double-corrupting them via the write-side translation) — this was verified
  necessary, not just theoretical: `config.py` was confirmed (byte-count check)
  to use CRLF throughout. Raises `RuntimeError` if any of the 3 target lines
  can't be located, rather than silently writing a partial/wrong result.
  Atomic write: `tempfile.mkstemp` in the same dir + `os.replace`, `os.remove`
  cleanup on any exception — same pattern as `generate_ground_truth.py`'s CSV
  write. Winner's `alpha`/`rrf_k` fall back to `config.ALPHA`/`config.RRF_K`
  when the winning approach doesn't use that parameter (e.g. lexical/vector
  winners still write *some* valid `ACTIVE_ALPHA`/`RRF_K`, just not swept ones).
- **Empty/missing input handling (spec requirement, no crash):** missing or
  all-malformed `ground_truth.csv` -> `logger.warning` + return
  `{"results": [], "winner": None}` immediately, WITHOUT touching the JSON/CSV/
  `config.py` outputs (overwriting previously-good evaluation artifacts with an
  empty result was judged worse than leaving them as-is). Malformed individual
  CSV rows (blank question, non-numeric `document_id`) are skipped with a
  `logger.warning`, not a hard failure. An empty `master_table` needed NO
  special-case code — `lexical_search`/`vector_search`/`hybrid_search` already
  return `[]` gracefully for zero-match queries, which naturally yields
  `hit_rate=mrr=0.0` rather than an exception. Infra-level failures (DB/schema
  missing entirely) deliberately propagate uncaught, consistent with
  `rag/generator.py`'s documented judgment call on retrieval-layer outages.
- No new `requirements.txt` entries — only stdlib (`csv`, `json`, `os`, `re`,
  `tempfile`, `pathlib`, `collections.abc.Callable`) plus existing internal
  `src.*` imports.
- **Self-review caught one bug before smoke testing was even needed to reveal
  it** (the `pipeline.py` RRF-branch bug above), found by cross-checking spec
  §9.2's literal wording against `pipeline.py`'s actual branching logic rather
  than assuming the already-built module was correct.
- **Runtime smoke test (throwaway venv: `python-dotenv sqlite-vec numpy
  onnxruntime transformers` — no `openai`/`google-genai`/`pydantic`/`tenacity`
  needed since this module never imports `src.llm`) found and fixed ONE MORE
  real bug that static analysis (`get_errors` + `pylanceFileSyntaxErrors`, both
  clean) completely missed:** `_replace_config_source()`'s inner loop wrote
  `for key, pattern in list(remaining.items())` — but `remaining` is
  `dict[str, str]` (key -> *replacement value*), not `dict[str, re.Pattern]`,
  so `pattern.match(body)` raised `AttributeError: 'str' object has no
  attribute 'match'` on the very first call. Fixed to look up the actual regex
  via `_ASSIGNMENT_PATTERNS[key]` and pop the replacement value separately.
  **Lesson reinforced (already in `/memories/debugging.md` but worth
  re-noting): Pylance's `get_errors` did NOT flag this even though `remaining`
  had an inferrable concrete type (`dict[str, str]`) and `.match` is not a str
  attribute — static analysis alone is not sufficient for this kind of bug;
  runtime smoke testing (even a synthetic/mocked one) is what actually caught
  it.** Test coverage after the fix (all passed): (a) metric math on synthetic
  known-rank data (hit@1, hit@3 partial rank 1/3, and a miss, verified exact
  hit_rate/MRR); (b) `config.py` rewrite happy path against a real copy of the
  actual file — confirmed exactly 3 lines differ (byte-for-byte compare of
  every other line, split on `\r\n`) and each new line's content/trailing
  comment is correct; (c) simulated `os.replace` failure (monkeypatched to
  raise) — confirmed the target file is byte-identical to before the call and
  zero leftover `.config_*` temp files remain; (d) full `evaluate_retrieval()`
  orchestration against monkeypatched `lexical_search`/`vector_search`/
  `hybrid_search`/`rerank` with a deterministic 3-question ground truth (one
  clean hit-rank-1, one partial hit-rank-2 lexically but rank-1 vector, one
  lexical-miss/vector-hit) — verified per-approach Hit Rate/MRR match hand-
  computed expected values for all 14 rows (including both ends of the alpha
  sweep), the JSON/CSV outputs contain all 14 rows with exactly one
  `is_winner=True`, the winner is written correctly into a fake `config.py`
  copy, and **the real `src/config.py` was confirmed byte-identical
  before/after the whole test run** (never touched, since the module always
  resolves its rewrite target via the mockable `_config_module.__file__`, not
  a hardcoded path); (e) missing `ground_truth.csv` -> confirmed
  `{"results": [], "winner": None}` returned and no JSON/CSV output files
  created. Temp venv + all temp files/dirs deleted afterward (verified via
  `Test-Path`, per the temp-file-DB cleanup hygiene lesson).
- `pylanceFileSyntaxErrors` + `get_errors` clean on both touched files
  (`evaluate_retrieval.py`, `retrieval/pipeline.py`) after the fixes. `git
  status`/`git diff --stat` confirmed only those two files changed —
  `src/config.py` untouched in the working tree (it's only rewritten at actual
  eval-run time, not during development).

## Cross-module static integration review #6 (after src/evaluation/evaluate_retrieval.py)
Re-read all 29 `src/` files in full (8 empty `__init__.py` + 21 substantive
modules) and ran `pylanceFileSyntaxErrors` individually on all 21 substantive
files, plus `get_errors` on the whole `src/` tree — **all clean, zero syntax
errors, zero diagnostics.**
- **No new bugs found this round** — `evaluate_retrieval.py`'s own build
  session (self-review + runtime smoke test + a follow-up user-requested
  review) already caught and fixed the only two real issues introduced by
  that work (the `pipeline.py` RRF-branch bug and the `_replace_config_source`
  pattern/value mix-up — see the entries above).
- **Cross-module wiring, re-verified end-to-end from scratch:** every
  constant every module imports from `config.py` exists with the expected
  type (traced all `from src.config import ...`/`import src.config as ...`
  usages across all 21 files); `LLMClient.structured()`'s
  `(parsed_model, LLMResponse)` return contract is implemented identically by
  `openai_client.py`/`gemini_client.py` and consumed identically by both
  callers (`rag/judge.py`, `evaluation/generate_ground_truth.py`);
  `insert_conversation()`/`insert_feedback()` parameter names match their
  call sites in `rag/generator.py`/`rag/judge.py` exactly (incl. the
  intentional `cost_usd`/`latency_seconds` -> `cost`/`response_time` mapping);
  `master_table`/`master_fts`/`master_vec` column names stay consistent
  across `knowledge_store.py` (schema), `ingestion/pipeline.py` (INSERT),
  `ingestion/resources.py` (`MasterTableRecord`), `retrieval/hybrid_search.py`
  (`Document`/SELECT), and `evaluation/generate_ground_truth.py`
  (`_fetch_records` SELECT); `embed()`/`score()` call shapes (incl. the
  `(query_vector,) = embed([query_text])` single-row unpack pattern) match
  every caller in `ingestion/` and `retrieval/`; `lexical_search`/
  `vector_search`/`hybrid_search`/`rerank`'s signatures match every call site
  in `retrieval/pipeline.py` and `evaluation/evaluate_retrieval.py` exactly,
  including the now-fixed `APPROACH_HYBRID` branch's `use_rrf=True` call
  matching `evaluate_retrieval.py`'s own Approach 3. **No import cycle:**
  dependency direction is still strictly `config -> {db, llm, models_onnx} ->
  {ingestion, retrieval} -> {rag, evaluation}` — verified by listing every
  module's internal imports from scratch, not reusing any prior review's map.
- **`requirements.txt` audit:** every third-party import across all 21
  substantive files (`dotenv`, `sqlite_vec`, `dlt`, `fitz`, `optimum.onnxruntime`,
  `transformers`, `onnxruntime`, `numpy`, `openai`, `google.genai`, `pydantic`,
  `tenacity`) is pinned; nothing pinned-but-unused. `evaluate_retrieval.py`
  needed no new entries (stdlib `csv`/`json`/`os`/`re`/`tempfile`/`pathlib`/
  `collections.abc.Callable` + existing internal `src.*` imports).
- **`__init__.py` audit:** all 8 (`src/`, `db/`, `evaluation/`, `ingestion/`,
  `llm/`, `models_onnx/`, `rag/`, `retrieval/`) confirmed empty (0 bytes).
- **Dead-code grep** (`print(`/`TODO`/`FIXME`/`pdb`/`breakpoint`): still only
  the one already-judged-intentional `print(load_info)` in
  `ingestion/pipeline.py`'s `run()` — no new leftovers anywhere, including the
  new `evaluation/evaluate_retrieval.py`.

## src/evaluation/evaluate_llm.py (spec §11.4) — pre-build design decisions (resolved before any code written)
Resolved in a planning conversation (2026-08-27), before the module exists —
apply these when actually building it, don't re-litigate:
1. **Judge cross-grading (avoids self-preference bias):** the judge LLM for
   grading `(Q, A, A')` must be the OPPOSITE provider from whichever model
   generated that A' — openai's answers are judged by gemini, gemini's
   answers are judged by openai. Never same-provider self-grading.
2. **Judge verdicts (`JudgeVerdict`, spec §11.4's own `good`/`bad` + `reasoning`
   schema — NOT `rag/judge.py`'s `RelevanceVerdict`) DO get persisted**, via
   two sanctioned additions to `src/db/monitoring_store.py` (deliberate schema
   extension, not a bug fix — `evaluate_llm.py`'s build session should treat
   this as in-scope, not "don't touch other modules"):
   a. Per-row verdicts -> existing `feedback` table, tied to the real
      `conversation_id` from that row's `generate_answer()` call, but tagged
      with a NEW, distinct `source` value `"eval_judge"` (not `"judge"`) so
      offline benchmark runs never blend with the live production relevance
      judge's `feedback` rows in a "judge score over time" dashboard query.
      Requires widening `CHECK (source IN ('user','judge'))` ->
      `CHECK (source IN ('user','judge','eval_judge'))` and
      `_VALID_FEEDBACK_SOURCES` accordingly.
   b. A NEW `llm_eval_runs` table (one row per `(model, run_timestamp)` per
      `make eval-llm` invocation: accuracy, total cost, avg latency,
      n_samples, is_winner) -- INSERTED every run, never overwritten. This is
      the actual backing store for a "trend over time" dashboard chart, since
      `evaluate_retrieval.py`-style JSON/CSV outputs are atomically
      OVERWRITTEN each run (correct for "current active config", useless for
      history). Needs a writer function (e.g. `insert_llm_eval_run(...)`,
      same self-contained-connection pattern as `insert_conversation`/
      `insert_feedback`) and an `init_db()` DDL addition.
   - **No migration concern right now:** confirmed via the workspace hygiene
     check (2026-08-27) that `data/monitoring.db` doesn't exist on disk yet
     (nothing has actually run `init_db()` for real against a persistent file
     yet), so this is a clean additive schema change, not a live migration.
3. **Forward note for the future `src/app/dashboard.py` build (spec §13.4,
   not yet built):** confirmed (2026-08-27) the `source="eval_judge"` split
   does NOT conflict with §13.4 item 4 ("Judge Relevance Distribution"
   bar chart of RELEVANT/PARTLY_RELEVANT/NON_RELEVANT counts) — that item's
   query MUST filter `source='judge'` (or equivalently `label IN
   ('RELEVANT','PARTLY_RELEVANT','NON_RELEVANT')`) so `eval_judge` rows never
   leak into it; the split is what protects that guarantee, not a source of
   conflict. HOWEVER: §13.4 also says "Do not add extra charts. The
   dashboard MUST contain exactly these five" — so the "judge/eval score
   trend over time" view (backed by `llm_eval_runs`) the user wants
   MUST NOT be added as a 6th chart inside `dashboard.py`. It needs its own
   separate surface (a distinct page/section, ad-hoc report, or notebook
   query against `llm_eval_runs`) — decide this explicitly when `dashboard.py`
   is actually built, don't silently bolt it onto the fixed 5-chart dashboard.
4. **Concurrency granularity:** sequential-per-model, parallel-within-model —
   run ALL ground-truth questions through one model (openai) via a single
   ThreadPoolExecutor batch, wait for it to fully finish, THEN run the same
   set through the other model (gemini) via a second batch. Never interleave
   both models' requests in one shared pool (gentler on each provider's rate
   limits, simpler to reason about/debug than one giant mixed to-do list).
5. **Failure handling:** skip-and-continue, matching every other module's
   established convention (`pdf_extractor.py`/`generate_ground_truth.py`/
   `evaluate_retrieval.py`) — one row's `generate_answer()`/judge-call failure
   is logged and excluded from that model's accuracy/cost/latency averages,
   never aborts the whole run. Track a per-model failure count explicitly —
   it doubles as the "reliability" input spec §11.4 requires for winner
   selection (a model failing more often is less reliable at comparable
   accuracy).
6. **No `config.py` write-back for the LLM-eval winner** (unlike
   `evaluate_retrieval.py`/spec §11.3, which explicitly mandates rewriting
   `ACTIVE_RETRIEVAL_APPROACH`/`ACTIVE_ALPHA`/`RRF_K`). Spec §11.4 only says
   the code should "select and output" the winning model — it never repeats
   the "write it back to config.py" instruction the way §11.3 does. Also,
   `DEFAULT_LLM_PROVIDER` is a much bigger-blast-radius setting than the
   retrieval-approach constants (it's the vendor every feature in the app
   depends on — cost, rate limits, reliability — not just an internal
   algorithm choice), and the winner here is chosen from a synthetic
   ground-truth benchmark, not real production traffic. `evaluate_llm()`
   reports the winner (JSON/CSV + logs) only; a human decides whether to
   then manually update `DEFAULT_LLM_PROVIDER`. `evaluate_llm.py` must NOT
   touch `src/config.py` at all.

## src/evaluation/evaluate_llm.py (spec §11.4) — built, per the pre-build design decisions above
Implemented exactly per the "pre-build design decisions" entry above (all 6
numbered items applied as-is, none re-litigated) plus SPEC.MD §11.4 itself.
- Single public function `evaluate_llm() -> dict`, `__main__` entrypoint for
  `make eval-llm`. No module-level mutable state.
- `JudgeVerdict(BaseModel)` (`verdict: Literal["good","bad"]`, `reasoning: str`)
  defined fresh in this module per spec §11.4's own schema — NOT
  `rag/judge.py`'s `RelevanceVerdict` (documented in the module docstring:
  that judge grades relevance-to-query, has no `A`/source-answer input).
- **A resolution:** `_resolve_answers()` does ONE batch
  `SELECT id, search_text FROM master_table` (mirrors
  `generate_ground_truth.py`'s `_fetch_records` join pattern) instead of one
  query per ground-truth row; rows whose `document_id` has no match, or whose
  `search_text` is empty, are skipped with `logger.warning`.
- **Cross-grading:** `_JUDGE_PROVIDER = {"openai": "gemini", "gemini": "openai"}`
  — the judge LLM for a row is always the opposite provider from the model
  that generated `A'`. Verified by smoke test (see below).
- **Concurrency:** `evaluate_llm()`'s `for model in _MODELS:` loop opens a
  *new* `ThreadPoolExecutor` per model and fully drains it
  (`list(executor.map(...))`) before the loop moves to the next model —
  sequential-per-model, parallel-within-model, never interleaved.
- **Failure handling:** `_evaluate_row()` never raises — a `generate_answer()`
  exception sets `failure_stage="generation"`; a judge `.structured()`
  exception sets `failure_stage="judge"`; both are logged
  (`exc_info=True`) and excluded from that model's `accuracy`/
  `avg_latency_seconds`, but counted in `n_failures`. A THIRD failure point
  (`insert_feedback()` persistence, after a successful judge call) is also
  caught+logged but deliberately does NOT count as a row failure or drop the
  verdict from in-memory aggregation — the verdict was already validly
  produced; only its DB write failed.
- **Qualitative failure analysis (own documented heuristic, not spec-
  mandated):** for every row judged `"bad"`, `_categorize_failure()` makes
  ONE extra `src.retrieval.pipeline.retrieve()` call (only for bad rows,
  since `GeneratedAnswer` doesn't expose the documents `generate_answer()`
  retrieved internally) and classifies zero-documents-retrieved as
  `"missing_context"`, documents-retrieved-but-not-the-ground-truth-id as
  `"irrelevant_context"` (uses the ground-truth `document_id` itself as the
  correctness check, not a score threshold — cross-encoder rerank scores are
  raw unbounded logits, not 0-1 normalized, so a threshold would be
  meaningless), and ground-truth-id-was-retrieved as `"hallucination"`.
- **Winner selection (`_select_winner`):** explicit deterministic rule —
  highest `accuracy` first, ties broken by fewer `n_failures` (reliability),
  then by lower `total_cost_usd` (cost efficiency) — satisfies spec §11.4's
  "accuracy, cost efficiency, and reliability" wording without inventing an
  opaque weighted score.
- **Outputs:** `LLM_EVAL_RESULTS_JSON` holds `{"rows": [...all per-row
  dicts...], "aggregates": {model: {...}}, "winner", "winner_reason"}`;
  `LLM_EVAL_RESULTS_CSV` holds only the flat per-row table (same rows list) —
  per-model aggregates/winner are JSON-only since they don't fit a flat
  per-row table. Both written via the same tempfile+`os.replace` atomic
  pattern as `evaluate_retrieval.py`.
- **`src/config.py`:** added `LLM_EVAL_RESULTS_JSON`/`LLM_EVAL_RESULTS_CSV`
  (same `DATA_DIR / "llm_eval_results.{json,csv}"` convention as the
  retrieval-eval constants). No other config.py changes — confirmed via a
  before/after byte-identical check in the smoke test (decision 6: no
  write-back).
- **`src/db/monitoring_store.py` extensions (sanctioned, per decision 2):**
  (a) `_VALID_FEEDBACK_SOURCES` widened to
  `frozenset({"user", "judge", "eval_judge"})` and the `feedback.source`
  CHECK constraint widened to match; `insert_feedback()`'s docstring updated
  to document `"eval_judge"`'s label vocabulary (`"good"`/`"bad"`) alongside
  `"judge"`'s (`RELEVANT`/`PARTLY_RELEVANT`/`NON_RELEVANT`). (b) new
  `llm_eval_runs` table (`id, model, run_timestamp, accuracy, total_cost,
  avg_latency, n_samples, n_failures, is_winner CHECK(0,1)`) + `init_db()`
  wiring + `insert_llm_eval_run(...)` writer (same self-contained-connection
  pattern as `insert_conversation`/`insert_feedback`, added to `__all__`).
  One row per `(model, run_timestamp)` per `evaluate_llm()` call (same
  `run_timestamp` for both models in one run), always INSERTED.
- No new `requirements.txt` entries — only stdlib (`csv`, `json`, `os`,
  `tempfile`, `concurrent.futures.ThreadPoolExecutor`, `dataclasses`,
  `datetime`, `typing.Literal`) plus already-pinned `pydantic` and existing
  internal `src.*` imports.
- **Runtime smoke-tested** in a throwaway venv (full non-ingestion deps:
  `python-dotenv sqlite-vec optimum[onnxruntime] transformers onnxruntime
  numpy openai google-genai pydantic tenacity` — needed because
  `evaluate_llm.py` transitively imports `rag.generator` ->
  `retrieval.pipeline` -> `models_onnx.embedder`/`llm.factory`). Seeded a
  real temp knowledge DB (3 `master_table` rows) + temp monitoring DB +
  temp `ground_truth.csv` (3 usable rows + 1 row pointing at a non-existent
  `document_id=99`, to test the skip-and-warn path). Monkeypatched
  `evaluate_llm.generate_answer`/`get_llm`/`retrieve` (module-level
  rebinding, since all three are imported via `from ... import`) to
  simulate: one generation-stage failure (openai/CE300), one judge-stage
  failure (gemini-judging-openai/BE200), one "bad" verdict with zero
  retrieved docs (openai/AC100, judged bad by gemini) and all-"good" gemini
  answers (judged by openai). Verified: `document_id=99` row correctly
  skipped with a warning; per-model `n_samples`/`n_judged`/`n_failures`/
  `accuracy`/`avg_latency_seconds`/`total_cost_usd`/`failure_analysis`
  (`{"missing_context": 1}` for openai) all matched hand-computed values
  exactly; cross-grading confirmed via `judge_provider` on every emitted row
  (openai rows always judged by "gemini" and vice versa); sequential-per-
  model execution order implicitly verified (each model's full batch
  completes — `n_samples` counts are correct per model — before the next
  starts); winner correctly picked gemini (strictly higher accuracy);
  JSON/CSV outputs well-formed and match in-memory results; `feedback`
  table got exactly 4 `source="eval_judge"` rows (one per row that was
  BOTH successfully generated AND successfully judged) with correct
  `good`/`bad` labels; `llm_eval_runs` got exactly 2 rows (one per model)
  with correct `is_winner`/`n_samples`/`n_failures`; a raw bypass INSERT
  with `source='bogus'` still raises a `CHECK`-constraint `IntegrityError`
  (confirms the widened CHECK constraint, not just the Python-level guard);
  empty-ground-truth-CSV and missing-ground-truth-CSV both returned
  `{"rows": [], "aggregates": {}, "winner": None, "winner_reason": None}`
  without touching any output; **`src/config.py` confirmed byte-identical
  before vs. after the full run** (decision 6 verified, not just assumed).
  All assertions passed. Temp venv + temp DB/CSV/JSON/CSV-output dirs
  deleted afterward (per the temp-file-DB cleanup hygiene lesson).
- `pylanceFileSyntaxErrors` + `get_errors` both clean on `evaluate_llm.py`,
  `monitoring_store.py`, and `config.py` after all edits.
- **No bugs found needing a review-round fix** — this build followed the
  already-resolved design-decision entry closely enough that the smoke test
  (which specifically exercised cross-grading, sequential/parallel
  concurrency, skip-and-continue at both failure points, the failure-
  analysis heuristic, and both new DB schema pieces end-to-end) passed on
  the first attempt with no code changes needed afterward.

## src/evaluation/evaluate_llm.py — follow-up review round (found and fixed a real gap)
User asked for one more review pass after the initial build above.
- **Real bug found:** `rag/generator.py`'s `generate_answer()` swallows most
  LLM-side failures internally (unknown provider, missing credentials, rate
  limits, timeouts, outages) and returns a canned fallback `GeneratedAnswer`
  (`model="generation-failed"`, the private `_GENERATION_FAILURE_MODEL`
  sentinel) instead of raising — see its own earlier Gemini-review-round
  entry above. `evaluate_llm.py`'s `_evaluate_row()` only detected
  generation failures via a *raised exception*, so a real LLM outage during
  an eval run would have silently been treated as a normal successful
  generation: the canned "service unavailable" text would be sent to the
  cross-graded judge, almost certainly scored `"bad"`, and counted toward
  accuracy/`failure_analysis` (likely misclassified as `"hallucination"`
  since retrieval would have returned real context) — WITHOUT incrementing
  `n_failures`, silently corrupting the "reliability" signal winner-selection
  depends on, and wasting a real judge-LLM call grading a non-answer.
- **Fix:** made `rag/generator.py`'s sentinel public — renamed
  `_GENERATION_FAILURE_MODEL` -> `GENERATION_FAILURE_MODEL`, added to its
  `__all__` (only a name change, no behavior change; `_GENERATION_FAILURE_MESSAGE`
  stays private since nothing outside the module needs the exact wording).
  `evaluate_llm.py` now imports it and checks `generated.model ==
  GENERATION_FAILURE_MODEL` immediately after a successful `generate_answer()`
  call: if true, logs a `logger.warning`, sets `failure_stage="generation"`
  (same field a raised exception would set) with a distinct
  `failure_reason`, and returns immediately WITHOUT calling the judge —
  saving a wasted judge-LLM call and keeping `generation_succeeded=False` so
  the row is correctly excluded from `avg_latency_seconds` too (the fallback
  path's `latency_seconds=0.0` would otherwise have dragged the average
  toward zero). Chose importing the real constant over duplicating the
  `"generation-failed"` string literal, to avoid drift risk if the sentinel
  value ever changes in `generator.py`.
- **Verified via a second focused smoke test** (throwaway venv, both models):
  monkeypatched `generate_answer` to always return the
  `GENERATION_FAILURE_MODEL` fallback, and `get_llm` to `raise
  AssertionError` if ever called — confirmed the judge is never invoked,
  both models' `n_failures=1`/`n_judged=0`/`accuracy=0.0`/
  `avg_latency_seconds=0.0`/`total_cost_usd=0.0`, every emitted row has
  `failure_stage="generation"` with the new fallback-specific reason text,
  and zero `feedback` rows were persisted. `pylanceFileSyntaxErrors` +
  `get_errors` clean on both `evaluate_llm.py` and `generator.py` after the
  edit; grepped for the old private name across `src/` — zero remaining
  references, rename fully applied.
- Rest of the file re-read line-by-line this round: no other issues found
  (aggregation math, winner selection, CSV/JSON writers, cross-grading
  wiring, and the `llm_eval_runs`/`feedback` persistence calls all still
  correct after the fix).

## Cross-module static integration review #7 (full re-read, after src/evaluation/evaluate_llm.py + its two review rounds)
Re-read all 30 `src/` files in full from scratch (8 empty `__init__.py` + 22
substantive modules) and ran `pylanceFileSyntaxErrors` individually on all 22
substantive files, plus `get_errors` on the whole `src/` tree — **all clean,
zero syntax errors, zero diagnostics.**
- **No new code bugs found this round** — the two prior `evaluate_llm.py`
  review rounds (initial build smoke test + the `GENERATION_FAILURE_MODEL`
  sentinel-detection fix) already caught the only real issues from that work.
- **One housekeeping finding, fixed:** `src/retrieval/SPEC.MD` was a
  byte-identical duplicate of the root `SPEC.MD` (confirmed via
  `Get-FileHash` on both + `git log --follow`, which showed it was
  accidentally committed inside the `retrieval` package in the very first
  commit). Not a functional bug (a `.md` file, never imported), but stray
  clutter inside a Python package — deleted it (`git status` confirms only
  a clean `D src/retrieval/SPEC.MD`, nothing else touched).
- **Cross-module wiring, re-verified end-to-end from scratch (not spot-
  checked, not reused from any prior review's map):** every constant every
  module imports from `config.py` exists with the expected type/annotation
  (`BASE_DIR`/`DATA_DIR`/`RAW_DIR`/`MODELS_DIR`/`EMBEDDING_MODEL_DIR`/
  `RERANKER_MODEL_DIR`/`KNOWLEDGE_DB`/`MONITORING_DB`/`GROUND_TRUTH_CSV`/
  `RETRIEVAL_EVAL_RESULTS_JSON`/`CSV`/`LLM_EVAL_RESULTS_JSON`/`CSV`/
  `EMBEDDING_MODEL_ID`/`RERANKER_MODEL_ID`/`EMBEDDING_DIM`/`OPENAI_MODEL`/
  `GEMINI_MODEL`/`DEFAULT_LLM_PROVIDER`/`TOP_K`/`FINAL_N`/`RRF_K`/
  `APPROACH_*`/`ALPHA`/`ACTIVE_ALPHA`/`ACTIVE_RETRIEVAL_APPROACH`/
  `PRICING_PER_1K_TOKENS`); `LLMClient.structured()`'s
  `(parsed_model, LLMResponse)` return contract is implemented identically
  by `openai_client.py`/`gemini_client.py` and consumed identically by all
  three callers (`rag/judge.py`, `evaluation/generate_ground_truth.py`,
  `evaluation/evaluate_llm.py`); `LLMResponse` field names
  (`text`/`prompt_tokens`/`completion_tokens`/`total_tokens`/
  `latency_seconds`/`cost_usd`/`model`) used identically everywhere;
  `insert_conversation()`/`insert_feedback()`/`insert_llm_eval_run()`
  parameter names match their call sites exactly in `rag/generator.py`,
  `rag/judge.py`, `evaluation/evaluate_llm.py` (incl. the intentional
  `cost_usd`/`latency_seconds` -> `cost`/`response_time` mapping at the
  `insert_conversation()` call site); `master_table`/`master_fts`/
  `master_vec` column names/order stay consistent across
  `knowledge_store.py` (schema), `ingestion/pipeline.py` (INSERT),
  `ingestion/resources.py` (`MasterTableRecord`), `retrieval/
  hybrid_search.py` (`Document`/SELECT), `evaluation/
  generate_ground_truth.py` (`_fetch_records`), and `evaluation/
  evaluate_llm.py` (`_resolve_answers`); `ground_truth.csv`'s
  `question,document_id` header/column order is produced identically by
  `generate_ground_truth.py` and consumed identically (incl. the
  `int(raw_id)` parse) by both `evaluate_retrieval.py`'s and
  `evaluate_llm.py`'s own `_load_ground_truth()` (two independent, not
  shared, implementations -- both correct, no drift); `embed()`/`score()`
  call shapes match every caller in `ingestion/` and `retrieval/`;
  `RetrievalResult.rewritten_query`/`.documents` match exactly what both
  `rag/generator.py` and `evaluation/evaluate_llm.py`'s
  `_categorize_failure()` read; `GeneratedAnswer`'s 9 fields (incl.
  `GENERATION_FAILURE_MODEL` sentinel now public) match exactly what
  `evaluate_llm.py` reads. **No import cycle:** dependency direction is
  still strictly `config -> {db, llm, models_onnx} -> {ingestion,
  retrieval} -> {rag, evaluation}` (evaluation also depends on rag), traced
  from every file's own top-level imports, not reused from any prior
  review's map.
- **`requirements.txt` audit (re-verified from scratch via a full grep of
  every `^import `/`^from \w` line across all 22 files):** all 12 pinned
  packages actually used (`python-dotenv`, `sqlite-vec`, `dlt`, `pymupdf`,
  `optimum[onnxruntime]`, `transformers`, `onnxruntime`, `numpy`, `openai`,
  `google-genai`, `pydantic`, `tenacity`); nothing pinned-but-unused,
  nothing used-but-unpinned.
- **`__init__.py` audit:** all 8 (`src/`, `db/`, `evaluation/`, `ingestion/`,
  `llm/`, `models_onnx/`, `rag/`, `retrieval/`) confirmed empty (0 bytes),
  re-verified by direct read, not assumed.
- **Dead-code grep** (`print(`/`TODO`/`FIXME`/`pdb`/`breakpoint`): still
  only the one already-judged-intentional `print(load_info)` in
  `ingestion/pipeline.py`'s `run()` (CLI stdout feedback for `make
  ingest`, alongside its own `logger.info`) -- no new leftovers anywhere.

## Workspace hygiene & security check (after src/evaluation/evaluate_llm.py + its review rounds)
User-requested pass, separate from the code review rounds above.
- **Real gap found & fixed:** `.gitignore` was never updated when
  `LLM_EVAL_RESULTS_JSON`/`LLM_EVAL_RESULTS_CSV` were added to `config.py` --
  it only listed `data/retrieval_eval_results.json`/`.csv` (the §11.3 eval's
  outputs), not the new `data/llm_eval_results.json`/`.csv` (§11.4's outputs).
  `data/*.db` already generically covers `monitoring.db`/`knowledge.db`, so
  that part was fine -- only the two new explicit CSV/JSON filenames were
  missing. Fixed by adding both lines next to the existing
  `retrieval_eval_results` entries. Lesson: adding a new generated-artifact
  path to `config.py` must come with a matching `.gitignore` entry in the
  same change -- add this to the standing checklist for any future
  `evaluate_*`/`generate_*` module that writes a new output file.
- **No temp-file/leftover-venv issues found:** `%TEMP%` swept for
  `*evalllm*`/`venv_*`/`*smoke*`/`*eval_retrieval*` -- zero hits, both
  smoke-test venvs and their marker files were fully cleaned up already (per
  the temp-file-DB cleanup hygiene lesson). `src/`/project root swept
  (`-Recurse`) for `_tmp_*`/`*.tmp`/`tmp*`/`*.pyc` -- zero hits. `data/`
  directory contains only `raw/` (no stray `.db`/`.csv` from a smoke test
  accidentally writing to the real `config.DATA_DIR` instead of a temp path).
  `__pycache__/` dirs exist under `src/` (normal Python bytecode cache from
  running the smoke tests) but are already `.gitignore`d and git-confirmed
  untracked (`git status --ignored`) -- not a hygiene issue, left as-is.
- **No hardcoded secrets/test keys found:** grepped all of `src/` for
  `sk-`/`api_key=`/`AIza`/`password=`/`secret=` patterns -- only false-positive
  matches on an unrelated code comment ("tests, etc."). No `.env` file exists
  on disk at all (`Test-Path` false); confirmed never tracked by git
  (`git ls-files` empty for `.env`) and correctly covered by `.gitignore`.
- **No unwanted dependencies:** `git diff requirements.txt` is empty --
  confirmed byte-for-byte unchanged this entire session (matches the
  established fact that `evaluate_llm.py` needed zero new pins).
- **No debug leftovers in the diff:** re-grepped for
  `print(`/`TODO`/`FIXME`/`pdb`/`breakpoint`/`localhost`/`127.0.0.1` across
  all of `src/` -- only the one already-judged-intentional
  `print(load_info)` in `ingestion/pipeline.py`. `git diff --stat` on the
  three modified existing files (`config.py` +2, `monitoring_store.py`
  +111/-2, `generator.py` +10/-8 lines) matches the expected scope of this
  session's changes with nothing extraneous.

## src/app/ (new package, spec.md section 13 -- Streamlit UI)
- `__init__.py` (empty), `qa_panel.py`, `dashboard.py`, `streamlit_app.py`.
  This is the final layer of the app -- consumes `rag/generator.py`,
  `rag/judge.py`, and `db/monitoring_store.py` exactly as those modules'
  own docstrings anticipated (`judge.py`'s live production judge had zero
  callers before this session; `monitoring_store.py`'s docstring already
  pointed dashboard queries here).
- **`config.py` addition:** `JUDGE_SAMPLE_RATE: float = 1.0` -- fraction of
  conversations the live judge (spec.md section 10.2) auto-grades from real
  traffic. Default `1.0` (judge every conversation, fully spec-compliant
  out of the box); a deployer can lower it for cost control with a one-line
  edit. Not exposed in the UI.
- **`qa_panel.py`:** single public `render_qa_panel() -> None`. Decision
  (not spec-mandated, resolved before writing code): render the answer +
  execution metrics via `st.write` FIRST, then -- gated by
  `_should_judge()`/`JUDGE_SAMPLE_RATE` -- call `judge_answer()`
  synchronously in the same request. This is the only way
  `feedback.source="judge"` rows (and therefore the dashboard's "Judge
  Relevance Distribution" chart) get populated from real traffic, since
  `judge.py` had no other caller. Judge failures are caught/logged and
  never affect the already-rendered answer.
  - Non-widget logic deliberately factored into three small, directly
    unit-testable functions (no `st.*` calls): `_should_judge(sample_rate)`
    (pure sampling gate), `_maybe_judge(user_query, answer,
    conversation_id)` (gate + try/except `judge_answer()` call), and
    `_handle_feedback(conversation_id, score)` (calls
    `insert_feedback(source="user", ...)`). `_submit_query()`/
    `_render_stored_result()` are the only functions touching `st.*`,
    calling into those three.
  - `st.session_state["qa_last_result"]` stores `conversation_id`, the
    rendered answer, and every execution metric (`prompt_tokens`/
    `completion_tokens`/`total_tokens`/`latency_seconds`/`cost_usd`) at
    submit time only -- a feedback-button click (which triggers a
    Streamlit rerun) re-renders from session state without re-calling
    `generate_answer()`/`judge_answer()` (would silently duplicate real
    LLM cost). Streamlit's own rerun-on-widget-interaction model means no
    manual `st.rerun()` call is needed after `insert_feedback()`.
  - Retrieval-layer exceptions from `generate_answer()` (its own
    documented infrastructure-failure case, deliberately NOT swallowed
    inside `generator.py` itself) are caught here at the UI boundary and
    shown via `st.error(...)`, so a DB/ONNX outage never crashes the whole
    Streamlit process. LLM-side failures never reach here at all --
    `generate_answer()` already swallows those internally
    (`GENERATION_FAILURE_MODEL` sentinel).
  - No provider selector in the UI (both `generate_answer()`/
    `judge_answer()` called with `provider=None`, falling back to
    `config.DEFAULT_LLM_PROVIDER`) -- spec section 13 never mentions one.
- **`dashboard.py`:** single public `render_dashboard() -> None`
  implementing EXACTLY the 5 spec-mandated items (Summary KPIs via
  `st.columns`+`st.metric`; Cost Over Time / Response Time Over Time via
  `st.line_chart`; Judge Relevance Distribution / User Feedback Comparison
  via `st.bar_chart`) -- no extra charts. `monitoring_store.py` exposes no
  read/aggregation queries by design (per its own docstring), so this
  module owns all the SQL.
  - SQL/aggregation factored into 5 small helper functions (`_fetch_*`),
    each taking a `sqlite3.Connection` and returning a plain dict or
    `pd.DataFrame` -- separate from the `st.*` rendering calls in
    `render_dashboard()`, specifically so they're directly unit-testable
    against a seeded DB without a running Streamlit app.
  - **Judge Relevance Distribution query filters `source='judge'` only**
    (never blends in `evaluate_llm.py`'s offline `source='eval_judge'`
    benchmark rows) -- exactly the split `monitoring_store.py`'s schema
    was built to protect (see its own comment/docstring).
  - Uncached by design (no `st.cache_data`) -- local, low-volume SQLite
    store; always showing the latest conversation/feedback on every rerun
    matters more than avoiding a repeated `SELECT`.
  - Empty-store handling: every `_fetch_*` helper returns sensible
    zero/empty values (`0`, `0.0`, all-zero label counts, empty
    `DataFrame`) instead of raising or returning `None`, so a fresh
    `data/monitoring.db` with zero conversations renders cleanly.
- **`streamlit_app.py`:** the `make up`/`streamlit run` entrypoint. Calls
  `src.db.knowledge_store.init_db()` and
  `src.db.monitoring_store.init_db()` once at import time (both
  idempotent `IF NOT EXISTS` DDL) before rendering anything, so the app
  never crashes against a fresh/empty `data/` directory. `st.set_page_config`
  + `st.title` + the two vertical sections in order (`render_qa_panel()`
  then `render_dashboard()`), per spec section 13.1's single-page,
  two-section layout.
- **New `requirements.txt` entries (verified via PyPI JSON API, both
  non-yanked as of 2026-08-27):** `streamlit==1.62.0` (latest,
  `requires_python>=3.10`) and `pandas==3.0.5` (latest, `requires_python>=3.11`,
  used explicitly in `dashboard.py` for `st.line_chart`/`st.bar_chart`
  input shaping -- pinned directly even though it's also a transitive
  streamlit dependency, per this repo's "every direct import gets its own
  pin" convention). Streamlit's other transitive deps (altair, pydeck,
  pyarrow, etc.) are left unpinned, same as this repo's existing precedent
  for other packages' transitive dependencies.
- **Runtime smoke-tested** (throwaway venv, `python-dotenv==1.2.3
  pandas==3.0.5 streamlit==1.62.0` ONLY -- deliberately lighter than the
  usual full-`requirements.txt` smoke tests, since `src.rag.generator`/
  `src.rag.judge` were stubbed into `sys.modules` *before* importing
  `src.app.qa_panel`, so importing it never pulls in the heavy
  ONNX/transformers/openai/google-genai chain). Verified:
  - `dashboard.py`'s 5 `_fetch_*` helpers against a seeded temp monitoring
    DB (3 conversations with known cost/response_time/tokens; 2 `judge`
    feedback rows [RELEVANT, NON_RELEVANT], 1 `eval_judge` row, 2 `user`
    rows [+1, -1]): KPI math matched hand-computed values exactly; the
    Judge Relevance Distribution correctly counted only the 2 `judge` rows
    and completely excluded the `eval_judge` row; User Feedback Comparison
    correctly showed up=1/down=1. A second empty temp DB (freshly
    `init_db()`'d, zero rows) confirmed every helper returns clean
    zero/empty values with no exceptions.
  - `qa_panel.py`'s `_should_judge(sample_rate=0.0)` never True and
    `_should_judge(sample_rate=1.0)` always True over 200 trials each;
    `_maybe_judge()` calls `judge_answer()` iff `_should_judge()` is True,
    and swallows (logs, does not raise) a simulated `judge_answer()`
    failure; `_handle_feedback(conversation_id, +1/-1)` calls
    `insert_feedback(conversation_id=..., source="user", score=+1/-1)`
    exactly once each, verified via mock assertion. `config.JUDGE_SAMPLE_RATE`
    confirmed `1.0` by default. All assertions passed. Temp venv, temp
    monitoring DBs, and the throwaway smoke-test script all deleted
    afterward (`git status --short` confirmed clean: only the intended
    `requirements.txt`/`config.py` diffs plus the new untracked `src/app/`
    package).
- `pylanceFileSyntaxErrors` + `get_errors` clean on all four new/changed
  files (`config.py`, `qa_panel.py`, `dashboard.py`, `streamlit_app.py`).
  Dead-code grep (`print(`/`TODO`/`FIXME`/`pdb`/`breakpoint`) across
  `src/app/`: zero hits.
- **Self-review finding (fixed before the smoke test, not a separate
  round):** the first draft of `qa_panel.py` inlined the judge-sampling
  gate and the feedback-button `insert_feedback()` call directly inside
  the `st.*`-calling render functions, which would have made them
  untestable without a real Streamlit script context (`st.session_state`/
  `st.button` raise outside one). Refactored into the three widget-free
  helpers (`_should_judge`/`_maybe_judge`/`_handle_feedback`) described
  above before running the smoke test, so the "testable logic separate
  from rendering" requirement is met by construction, not by mocking
  Streamlit itself.

## src/app/streamlit_app.py -- follow-up review round (found and fixed a real bug)
User asked for a second review pass after the initial `src/app/` build above.
- **Real bug found:** `init_knowledge_db()`/`init_monitoring_db()` were
  called as plain module-level statements. Streamlit re-executes the
  *entire* script top-to-bottom on every widget interaction (every Submit
  click, every +1/-1 click, etc.), so both `init_db()` calls -- each
  opening a fresh sqlite3 connection and running several `CREATE TABLE IF
  NOT EXISTS`/index/trigger statements -- were silently re-running on
  EVERY single rerun, not just once at startup as the design decision said
  ("calls both init_db()s once at startup"). Not a correctness bug
  (idempotent DDL), but real, unnecessary DB round-trip overhead on every
  interaction.
- **Fix:** wrapped both calls in a `@st.cache_resource`-decorated
  `_init_stores()` helper -- Streamlit's own supported mechanism for "run
  once per server process, skip on every subsequent rerun" (distinct from
  `@st.cache_data`, which caches return values keyed on arguments;
  `@st.cache_resource` is for side-effecting singleton initialization like
  this).
- **Verified via a throwaway venv check** (streamlit+pandas only): wrapped
  a call-counting function in `@st.cache_resource` and called it 5 times
  in a loop (simulating 5 script reruns) -- confirmed the underlying
  function body ran exactly once. Re-ran `pylanceFileSyntaxErrors`/
  `get_errors` on `streamlit_app.py` -- clean.
- **Also verified (previously untested gap):** the earlier smoke test only
  exercised `dashboard.py`'s `_fetch_*` data-shaping helpers, never the
  actual `st.line_chart`/`st.bar_chart` calls on the empty-store DataFrame
  shapes those helpers produce. Ran a second throwaway check calling the
  real `st.line_chart`/`st.bar_chart`/`st.metric` with the exact
  empty-case DataFrames (0-row `columns=["cost"]`/`columns=["response_time"]`,
  and the all-zero-count judge/feedback DataFrames) -- all rendered
  without raising (only a harmless Altair `UserWarning` on the
  genuinely-0-row charts about inferring vega-lite type from empty data,
  purely cosmetic). Confirms the "handles an empty monitoring store
  gracefully" claim is actually true, not just assumed.
- No other new findings this round -- `qa_panel.py`'s sampling-gate/judge-
  dispatch/feedback-dispatch separation and `dashboard.py`'s SQL/labels
  were re-read line-by-line and remain correct. All throwaway venvs/scripts
  from this review round deleted afterward; `git status --short` confirmed
  clean scope (`docs/PROJECT_NOTES.md`, `requirements.txt`, `config.py`
  modified + new untracked `src/app/`).

## Cross-module static integration review #8 (final -- after src/app/, closes out spec.md's whole file tree)
User asked whether another bug-hunt round was warranted after the two
`src/app/` review rounds above; judged a third open-ended re-read as low
value, and ran this repo's standard end-of-module integration checklist
instead (see the "Reusable prompt: end-of-module review" entry earlier
in this file).
- **No import cycle:** grepped for `from src.app`/`import src.app`
  anywhere in `src/` -- only `streamlit_app.py` itself imports from
  `src.app` (`dashboard`/`qa_panel`); no other module imports `src.app`.
  `src/app/` is a pure leaf consumer, dependency direction unchanged:
  `config -> {db, llm, models_onnx} -> {ingestion, retrieval} ->
  {rag, evaluation} -> app`.
- **`__init__.py` audit:** all 9 packages (`src/`, `app/`, `db/`,
  `evaluation/`, `ingestion/`, `llm/`, `models_onnx/`, `rag/`,
  `retrieval/`) confirmed 0 bytes via direct byte-length check.
- **Dead-code grep** (`print(`/`TODO`/`FIXME`/`pdb`/`breakpoint`) across
  all of `src/`: still only the one already-judged-intentional
  `print(load_info)` in `ingestion/pipeline.py` -- nothing new introduced
  by `src/app/`.
- **Signature matching, re-verified from scratch:** `GeneratedAnswer`'s
  7 fields (`conversation_id`/`answer`/`prompt_tokens`/`completion_tokens`/
  `total_tokens`/`latency_seconds`/`cost_usd`) match exactly what
  `qa_panel._submit_query` reads; `insert_feedback(conversation_id,
  source, score=None, label=None, explanation=None, db_path=...)` matches
  `_handle_feedback`'s call exactly; `judge_answer(user_query, answer,
  conversation_id, provider=None)` matches `_maybe_judge`'s call exactly.
- **No new bugs found.** This closes out the integration review cycle for
  the entire `src/` tree -- `src/app/` was the last package in spec.md's
  file tree (section 13).

## Cross-module static integration review #9 (full re-read, re-verified per user request after #8)
User asked to run the repo's full formal "end-of-module review" prompt
verbatim (re-read every file fresh, syntax-check every file individually,
full requirements.txt audit) rather than trust review #8's lighter/
targeted version. Executed the full checklist:
- **Re-read all 25 substantive `src/` files in full, from scratch**
  (config.py, db/knowledge_store.py+monitoring_store.py, ingestion's 3
  files, llm's 4 files, models_onnx's 3 files, retrieval's 4 files,
  rag's 2 files, evaluation's 3 files, app's 3 files) -- byte-for-byte
  match what memory/docs already claimed; no hand-edits found.
- **`pylanceFileSyntaxErrors` run individually on all 25** -- clean.
- **Full `requirements.txt` audit** (grepped every `^import`/`^from` line
  across all of `src/`): all 14 pinned packages (`python-dotenv`,
  `sqlite-vec`, `dlt`, `pymupdf`, `optimum[onnxruntime]`, `transformers`,
  `onnxruntime`, `numpy`, `openai`, `google-genai`, `pydantic`,
  `tenacity`, `streamlit`, `pandas`) map to an actual import; nothing
  unpinned, nothing pinned-but-unused.
- **Import cycle / `__init__.py` audit**: reconfirmed clean (same result
  as review #8, no changes since).
- **New finding worth recording (not a bug, but a real risk that was
  checked, not assumed):** `config.JUDGE_SAMPLE_RATE` (added for
  `src/app/`) sits near `ACTIVE_RETRIEVAL_APPROACH`/`ACTIVE_ALPHA`/
  `RRF_K`, which `evaluate_retrieval.py`'s `_replace_config_source()`
  rewrites in-place via regex line-matching (`_ASSIGNMENT_PATTERNS`) and
  requires byte-exact CRLF preservation elsewhere in the file. Explicitly
  re-verified (byte-level regex count check) that `config.py` is still
  100% CRLF (105/105 line endings, zero bare-LF) and that all three
  `_ASSIGNMENT_PATTERNS` regexes still match their target lines exactly
  -- the `JUDGE_SAMPLE_RATE` edit did not disturb this fragile
  cross-module contract. Worth this explicit check any time a future
  edit touches `config.py`, since `_replace_config_source()` raises
  `RuntimeError` (not silent corruption) if a pattern ever stops
  matching, but only at actual `make eval-retrieval` runtime.
- **No new bugs found.** Codebase confirmed clean and stable; no further
  review round planned unless new code is added.

## TODO when building README.md (spec.md §15.1, matrix items #8/#9)
Don't forget: items #8/#9 in the §16 traceability matrix require the
`master_table.id` ground-truth rationale and the FK-extension
future-proofing pattern to be explained **in the README**, not just in
code comments (`db/knowledge_store.py` already documents both in-code).
When writing README.md, include a section (or fold into the schema/
data-model section) covering:
- **Why `master_table.id` exists:** it's the "answer key" join column
  the ground-truth methodology depends on -- `generate_ground_truth.py`
  generates ~5 questions per record and pairs each with that record's
  `id`; `evaluate_retrieval.py` later checks whether the correct `id`
  appears in a question's retrieved results (Hit Rate/MRR). Link to the
  spec's cited methodology:
  https://github.com/DataTalksClub/llm-zoomcamp/blob/main/04-evaluation/lessons/03-ground-truth-batch.md
- **Why `master_table` must never gain new columns directly:** future
  MOSFET attributes (electrical/thermal specs, packaging, pricing) must
  be added via new FK-linked extension tables referencing
  `master_table.id` (worked example already in `knowledge_store.py`'s
  comments), never by altering `master_table` itself -- keeps every
  existing consumer of that table stable as the schema grows.
</content>
