# Technical Specification: MOSFET Selection RAG Application (`spec.md`)

**Document Version:** 1.0.0
**Status:** Code-Ready Blueprint
**Audience:** Senior Python Developer (Implementation Agent)
**Directive:** Implement the codebase *strictly* from this specification. Where a library, model, filename, table name, or formula is named explicitly, it is **mandatory** and must not be substituted. Where behavior is described, implement it exactly as written.

---

## 1. Overview & Problem Statement

### 1.1 Purpose
Build an end-to-end **Retrieval-Augmented Generation (RAG)** application that lets an electronics design engineer perform **preliminary MOSFET selection** from an existing corpus of PDF datasheets using **natural language** (e.g., *"I want MOSFETs for a fast-switching application, with RoHS compliance"*).

### 1.2 Guiding Principles (Non-Negotiable)
- **Python-first:** All application logic, pipelines, and UI are Python.
- **Workflow automation:** Every pipeline stage is runnable via a single `make` command.
- **Data privacy:** The knowledge base and monitoring stores are local **SQLite** files. Embedding and re-ranking inference run **locally on CPU** via **ONNX**.
- **LLM provider abstraction:** The generation LLM MUST sit behind a swappable interface so the team can switch between cloud providers (OpenAI, Google) and local/open-source models without touching business logic.

### 1.3 High-Level Data Flow

```
                    ┌───────────────────────── Streamlit UI ─────────────────────────┐
                    │   [ Q&A Panel ]                    [ Monitoring Dashboard ]     │
                    └───────┬─────────────────────────────────────────▲──────────────┘
                            │ user query                               │ telemetry / feedback
                            ▼                                          │
   Stage 0: Query Rewrite (LLM) ─► Stage 1: Hybrid Search (FTS5 + Vector)
                            │                                          │
                            ▼                                          │
   Stage 2: Cross-Encoder Re-rank (ONNX) ─► Top-N context ─► RAG Generation (LLM Abstraction)
                            │                                          │
                            ├──────────► LLM-as-Judge relevance ───────┤
                            ▼                                          ▼
                    conversations table  ◄──── FK ────►  feedback table   (monitoring.db, SQLite)

   Offline: dlt Ingestion (PDF page 1) ─► master_table (knowledge.db, SQLite + vector ext)
   Offline: Evaluation (retrieval + LLM) ─► results JSON/CSV ─► winner written to config.py
```

---

## 2. Mandatory Tech Stack

| Concern | Technology (Exact) | Notes |
|---|---|---|
| Language | **Python 3.11** | Pin in Docker + `requirements.txt`. |
| Frontend | **Streamlit** | Single-file or modular app; minimal code. |
| Ingestion | **dlt (Data Load Tool)** | REQUIRED. No standalone ingestion scripts. |
| PDF parsing | **pymupdf (`fitz`)** or **pdfplumber** | First page only. |
| Knowledge Base | **SQLite** + vector extension **`sqlite-vec`** (fallback `sqlite-vss`) | Vector storage + retrieval. |
| Lexical Search | **SQLite FTS5** (BM25) | Mandatory for keyword search. |
| Embedding Model | **`sentence-transformers/multi-qa-MiniLM-L6-cos-v1`** | Exported and run in **ONNX**. |
| Re-ranker | **`cross-encoder/ms-marco-MiniLM-L-6-v2`** | Exported and run in **ONNX**. |
| ONNX Runtime | **`onnxruntime`** (CPU) + **`optimum[onnxruntime]`** | For export + inference. |
| LLM (Cloud A) | **OpenAI `gpt-5.4-mini`** | Query rewrite, generation, judge. |
| LLM (Cloud B) | **Google `gemini-2.5-flash`** | Swappable alternative. |
| Structured Output | **Pydantic v2 (`BaseModel`)** | Ground truth, judge verdicts. |
| Secrets | **python-dotenv** | Load `./.env`. |
| Monitoring Store | **SQLite** | `conversations`, `feedback` tables. |
| Concurrency | **`concurrent.futures.ThreadPoolExecutor`** | Batch evaluation. |
| Orchestration | **Docker + `docker-compose.yml`** | Single-command stack. |
| Task Runner | **Makefile** | `make ingest`, `make eval-retrieval`, `make up`, etc. |

> **Dependency pinning is mandatory.** Every package MUST have an exact `==` version in `requirements.txt` (or `Pipfile` with lock).

---

## 3. Project File Structure

Implement the following structure exactly. Create empty `__init__.py` files where packages are implied.

```
mosfet-rag/
├── .env.example                  # Template for required secrets (NEVER commit real .env)
├── .gitignore
├── docker-compose.yml            # Orchestrates the full stack
├── Dockerfile                    # App image (Python 3.11 slim)
├── Makefile                      # make ingest | eval-retrieval | eval-llm | up | down | ...
├── requirements.txt              # Pinned dependency versions
├── README.md                     # Non-expert documentation (see §12)
├── docs/
│   ├── setup.md                  # (optional split) setup & env vars
│   └── usage.md                  # (optional split) usage & examples
│
├── data/
│   ├── raw/                      # Source MOSFET PDF datasheets (downloaded by reviewer)
│   ├── knowledge.db              # SQLite KB (master_table + FTS5 + vectors) [generated]
│   ├── monitoring.db             # SQLite telemetry (conversations, feedback) [generated]
│   ├── ground_truth.csv          # Synthetic eval dataset [generated]
│   ├── retrieval_eval_results.json
│   └── retrieval_eval_results.csv
│
├── models/
│   ├── embedding/                # ONNX export of multi-qa-MiniLM-L6-cos-v1
│   └── reranker/                 # ONNX export of ms-marco-MiniLM-L-6-v2
│
├── Skills/
│   └── datasheet-1.0.0/
│       └── SKILL.md              # REFERENCE extraction guide (developer MUST adapt this)
│
└── src/
    ├── __init__.py
    ├── config.py                 # Central config; holds WINNING retrieval approach + α/k
    ├── db/
    │   ├── __init__.py
    │   ├── knowledge_store.py     # master_table schema, FTS5, vector ext init, queries
    │   └── monitoring_store.py    # conversations + feedback schema and writers
    ├── ingestion/
    │   ├── __init__.py
    │   ├── pipeline.py            # dlt pipeline definition (entrypoint for `make ingest`)
    │   ├── pdf_extractor.py       # First-page extraction (adapts Skills/datasheet-1.0.0/SKILL.md)
    │   └── resources.py           # dlt @dlt.resource / @dlt.source definitions
    ├── models_onnx/
    │   ├── __init__.py
    │   ├── export.py              # Exports both HF models to ONNX (run once / build step)
    │   ├── embedder.py            # ONNX embedding inference (mean-pool + normalize)
    │   └── reranker.py            # ONNX cross-encoder inference
    ├── retrieval/
    │   ├── __init__.py
    │   ├── query_rewriter.py      # Stage 0
    │   ├── hybrid_search.py       # Stage 1 (FTS5/BM25 + vector + weighted fusion + RRF)
    │   ├── reranker_stage.py      # Stage 2 (cross-encoder re-ranking)
    │   └── pipeline.py            # Orchestrates Stage 0 → 1 → 2 (public retrieve())
    ├── llm/
    │   ├── __init__.py
    │   ├── base.py                # Abstract LLMClient interface (provider-agnostic)
    │   ├── openai_client.py       # gpt-5.4-mini implementation
    │   ├── gemini_client.py       # gemini-2.5-flash implementation
    │   └── factory.py             # get_llm(provider) → returns LLMClient
    ├── rag/
    │   ├── __init__.py
    │   ├── generator.py           # Builds prompt, calls LLM, returns answer + usage metrics
    │   └── judge.py               # Built-in LLM relevance judge (RELEVANT/PARTLY/NON)
    ├── evaluation/
    │   ├── __init__.py
    │   ├── generate_ground_truth.py
    │   ├── evaluate_retrieval.py
    │   └── evaluate_llm.py
    └── app/
        ├── __init__.py
        ├── streamlit_app.py       # UI entrypoint (Q&A + dashboard)
        ├── qa_panel.py            # Q&A section components
        └── dashboard.py           # Monitoring dashboard (exactly 5 charts/metrics)
```

---

## 4. Configuration & Environment (`src/config.py`, `.env`)

### 4.1 Environment Variables (loaded via `python-dotenv` from `./.env`)
| Variable | Purpose | Required |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI (`gpt-5.4-mini`) access | Yes (for OpenAI backbone) |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Google (`gemini-2.5-flash`) access | Yes (for Gemini backbone) |

- Provide `.env.example` documenting all keys with placeholder values.
- `config.py` MUST call `load_dotenv()` at import time and expose typed config constants.

### 4.2 `config.py` Responsibilities
- Paths: `DATA_DIR`, `RAW_DIR`, `KNOWLEDGE_DB`, `MONITORING_DB`, `GROUND_TRUTH_CSV`, ONNX model dirs.
- Model IDs: embedding, reranker, and both LLM identifiers.
- Retrieval params: `TOP_K` (candidates from Stage 1, default 20), `FINAL_N` (after re-rank, default 5), `ALPHA` (hybrid weight), `RRF_K`.
- **Winning retrieval approach:** a mutable/writable constant `ACTIVE_RETRIEVAL_APPROACH` and `ACTIVE_ALPHA` that the evaluation pipeline programmatically overwrites (see §11.3). Production RAG reads these values.
- Pricing table (USD per 1K tokens) per model for cost estimation.
- Default generation provider (`gpt-5.4-mini` or `gemini-2.5-flash`).

---

## 5. Database Schema & Relational Design

### 5.1 Knowledge Base — `master_table` (in `data/knowledge.db`)

Create the **primary table named `master_table`** with this **exact** column set and order:

| # | Column | Type | Constraints | Description |
|---|---|---|---|---|
| 1 | `id` | INTEGER | **PRIMARY KEY** (unique) | Stable unique record ID. **Strictly required for generating ground-truth evaluation data** per the batch ground-truth methodology: `https://github.com/DataTalksClub/llm-zoomcamp/blob/main/04-evaluation/lessons/03-ground-truth-batch.md`. |
| 2 | `component_type` | TEXT | | e.g., "N-Channel MOSFET". |
| 3 | `manufacturer_name` | TEXT | | e.g., "Infineon". |
| 4 | `part_number` | TEXT | | e.g., "IRF540N". Used as human-readable `document_id`. |
| 5 | `search_text` | TEXT | | Concatenation of **Descriptions + Features + Applications**. |
| 6 | `search_vector` | BLOB / vector | | Embedding of `search_text` (see §7). Stored via `sqlite-vec` virtual table / column. |

**Supporting structures on the same DB:**
- **FTS5 virtual table** (e.g., `master_fts`) indexing `search_text` (and optionally `part_number`, `manufacturer_name`) to enable **BM25** lexical scoring. Keep it synchronized with `master_table` via triggers or explicit inserts during ingestion.
- **Vector index** via `sqlite-vec` (preferred) virtual table keyed by `master_table.id` storing `search_vector`, queried with **cosine similarity/distance**.

### 5.2 Future-Proofing Requirement (Mandatory Statement)
The schema **MUST be designed for expandability**. Additional component-attribute tables (e.g., `electrical_specs`, `thermal_specs`, `packaging`) may be added later. Each such table MUST reference `master_table.id` as a **FOREIGN KEY** so extra MOSFET information can be appended and joined without altering `master_table`. Document this 1-to-many extension pattern in code comments and README.

### 5.3 Monitoring DB — two tables (in `data/monitoring.db`)

**Table `conversations`:**
| Column | Type | Notes |
|---|---|---|
| `id` (`conversation_id`) | TEXT/UUID | Primary key. |
| `query` | TEXT | Raw user query. |
| `rewritten_query` | TEXT | Stage 0 output (nullable). |
| `answer` | TEXT | LLM-generated answer. |
| `prompt` | TEXT | Full prompt text sent to the LLM. |
| `model` | TEXT | Model used for generation. |
| `prompt_tokens` | INTEGER | |
| `completion_tokens` | INTEGER | |
| `total_tokens` | INTEGER | |
| `response_time` | REAL | Latency in seconds. |
| `cost` | REAL | Estimated USD. |
| `timestamp` | TEXT/DATETIME | **Timezone-aware** (UTC ISO-8601). |

**Table `feedback`:**
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key (autoincrement). |
| `conversation_id` | TEXT | **FOREIGN KEY → `conversations.id`**. |
| `source` | TEXT | `"user"` or `"judge"`. |
| `score` | INTEGER | `+1` / `-1` for user; mapped value for judge (see §9.2). |
| `label` | TEXT | Judge label: `RELEVANT` / `PARTLY_RELEVANT` / `NON_RELEVANT` (nullable for user). |
| `explanation` | TEXT | Judge reasoning (nullable for user). |
| `timestamp` | TEXT/DATETIME | Timezone-aware. |

---

## 6. LLM Abstraction Layer (`src/llm/`)

Because provider-swapping is a core principle, all LLM access MUST go through one interface.

### 6.1 `base.py` — Abstract Interface
Define an abstract `LLMClient` with, at minimum:
- `complete(prompt: str, system: str | None = None, **kwargs) -> LLMResponse`
- `structured(prompt: str, schema: type[BaseModel], **kwargs) -> tuple[BaseModel, Usage]` — returns a validated Pydantic object plus usage.
- Return a dataclass/`LLMResponse` bundling: `text`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `latency_seconds`, `cost_usd`, `model`.

### 6.2 Implementations
- `openai_client.py` → `gpt-5.4-mini` (uses `OPENAI_API_KEY`).
- `gemini_client.py` → `gemini-2.5-flash` (uses `GEMINI_API_KEY` / `GOOGLE_API_KEY`).
- Each implementation MUST populate token usage and compute `cost_usd` from the `config.py` pricing table.

### 6.3 `factory.py`
- `get_llm(provider: str) -> LLMClient` returns the correct client. Providers: `"openai"`, `"gemini"`. This factory is the single swap point used by query rewrite, generation, judge, and evaluation.

---

## 7. ONNX Model Layer (`src/models_onnx/`)

### 7.1 Export (`export.py`)
- Export **`sentence-transformers/multi-qa-MiniLM-L6-cos-v1`** to ONNX → `models/embedding/`.
- Export **`cross-encoder/ms-marco-MiniLM-L-6-v2`** to ONNX → `models/reranker/`.
- Use `optimum[onnxruntime]`. Export MUST run at build time (Docker) or via `make export-models`.

### 7.2 Embedder (`embedder.py`)
- Load ONNX embedding model with `onnxruntime` (CPU provider).
- Tokenize → run session → **mean-pool** token embeddings using the attention mask → **L2-normalize** (required for cosine similarity).
- Expose `embed(texts: list[str]) -> np.ndarray`. Used during ingestion and query-time vector search.

### 7.3 Reranker (`reranker.py`)
- Load ONNX cross-encoder with `onnxruntime` (CPU).
- Expose `score(query: str, docs: list[str]) -> list[float]`, scoring each `(query, document)` pair.

> **Rationale to document in code:** ONNX + CPU inference keeps embedding/re-ranking **local and fast**, satisfying the data-privacy principle.

---

## 8. Data Ingestion Pipeline (`src/ingestion/`)

### 8.1 Framework Constraint
- **MUST use `dlt` (Data Load Tool).** A plain standalone Python ingestion script is **explicitly forbidden**. The pipeline entrypoint (`pipeline.py`) is invoked by `make ingest`.

### 8.2 Source
- Ingest raw MOSFET PDF files from **`/data/raw`**.

### 8.3 Extraction Logic
- The developer MUST **adapt and use the reference file `Skills/datasheet-1.0.0/SKILL.md`** to guide field extraction. Modify it as needed for these datasheets.
- **Only the first page** of each datasheet is processed. No other pages.

### 8.4 Field Mapping
Extract these six data points per datasheet:

| Extracted Field | Destination |
|---|---|
| (1) Component Type | `master_table.component_type` |
| (2) Manufacturer Name | `master_table.manufacturer_name` |
| (3) Part Number | `master_table.part_number` |
| (4) Descriptions | → concatenate into `search_text` |
| (5) Features | → concatenate into `search_text` |
| (6) Applications | → concatenate into `search_text` |

- After concatenation, embed `search_text` via the **ONNX embedder** (§7.2) and write the vector to `master_table.search_vector`.
- Populate the FTS5 mirror and vector index as part of the load step.

### 8.5 Graceful Error Handling (Mandatory)
- Not every datasheet contains sections literally titled **Descriptions**, **Features**, or **Applications**.
- If a section is missing, the pipeline **MUST ignore that section gracefully**, append whatever sections *are* found, and continue **without raising an error**. A record with partial `search_text` is valid. Log a warning; never crash the run.

---

## 9. Retrieval Pipeline (`src/retrieval/`)

The public entrypoint `pipeline.retrieve(user_query: str) -> list[Document]` orchestrates the two-stage flow below (Stage 0 precedes it).

### 9.1 Stage 0 — Query Rewriting (`query_rewriter.py`)
- **Before retrieval**, pass the user's raw input to an LLM (`gpt-5.4-mini` or `gemini-2.5-flash` via the abstraction) to **expand acronyms and technical constraints** into an optimized search query (e.g., expand "RoHS", "fast-switching" → relevant technical terms).
- Output = rewritten query string, which is fed into Stage 1.

### 9.2 Stage 1 — Hybrid Search (`hybrid_search.py`)
- **Lexical:** Run **SQLite FTS5 BM25** over `search_text` to get keyword scores.
- **Semantic:** Embed the rewritten query (ONNX embedder) and run **cosine similarity** vector search via `sqlite-vec`.
- **Score normalization:** Min-max normalize each score list to `[0, 1]` before fusion.
- **Weighted fusion (mandatory formula):**

  $$\text{final\_score} = (\alpha \times \text{vector\_score}) + \big((1-\alpha) \times \text{keyword\_score}\big)$$

  where `α = config.ACTIVE_ALPHA`.
- Also implement **Reciprocal Rank Fusion (RRF)** as an alternative fusion strategy (used by evaluation Approach 3 and tuned in Approach 4): `score = Σ 1/(k + rank_i)`, with `k = config.RRF_K`.
- Return **Top-K** candidate documents (`config.TOP_K`).

### 9.3 Stage 2 — Cross-Encoder Re-ranking (`reranker_stage.py`)
- Take the Top-K candidates from Stage 1.
- Score every `(query, document)` pair with the ONNX **`cross-encoder/ms-marco-MiniLM-L-6-v2`**.
- **Sort documents descending by cross-encoder relevance score.**
- Return the top `FINAL_N` documents. This sorted list is the **final retrieval output** injected into the LLM context window.

---

## 10. RAG Generation & Built-in Judge (`src/rag/`)

### 10.1 Generator (`generator.py`)
- Input: user query + final re-ranked documents (§9.3).
- Build a grounded prompt (system instruction: answer only from provided datasheet context; cite `part_number`s).
- Call the LLM via the abstraction layer; capture answer + full usage metrics (tokens, latency, cost).
- Return an object containing `answer`, `prompt`, and all execution metrics for monitoring capture.

### 10.2 Built-in LLM Relevance Judge (`judge.py`)
- Immediately after generation, an automated LLM judge evaluates the **relevance of the system's own answer**.
- MUST use **Pydantic structured output**. Schema:
  ```python
  class RelevanceVerdict(BaseModel):
      label: Literal["RELEVANT", "PARTLY_RELEVANT", "NON_RELEVANT"]
      explanation: str
  ```
- Persist the judge result to the `feedback` table with `source="judge"` (map label → optional numeric `score`; keep `label` + `explanation`).

---

## 11. Evaluation Framework (`src/evaluation/`)

### 11.1 Ground Truth Generation (`generate_ground_truth.py`)
- Use an LLM (`gpt-5.4-mini` / `gemini-2.5-flash`, or GPT-4o-mini-class) with **Pydantic structured output** — schema named **`Questions`**:
  ```python
  class Questions(BaseModel):
      questions: list[str]
  ```
- For **every** MOSFET record in `master_table`, generate **~5 realistic engineering queries** (search by specs, RoHS compliance, switching speed, package, etc.).
- Save to **`data/ground_truth.csv`** with exactly two core fields:
  - `question` — the generated query.
  - `document_id` — the target MOSFET **part number / record `id`**.

### 11.2 Retrieval Evaluation (`evaluate_retrieval.py`)
Measure and compare **at least 4 distinct retrieval configurations** against the **same** `ground_truth.csv`:

1. **Approach 1 — Lexical Keyword Search:** SQLite FTS5 / BM25 only.
2. **Approach 2 — Dense Vector Search:** ONNX `multi-qa-MiniLM-L6-cos-v1` embeddings + cosine distance.
3. **Approach 3 — Basic Hybrid Search:** keyword + vector combined via **RRF or weighted-score fusion**.
4. **Approach 4 — Two-Stage Hybrid + Cross-Encoder Re-ranking & Parameter Tuning:** full hybrid feeding candidates into ONNX `ms-marco-MiniLM-L-6-v2` cross-encoder, evaluated **across parameter variations** (sweep hybrid weight **α from 0.0 → 1.0**, and/or RRF constant **k**).

**Metrics (compute for each approach):**
- **Hit Rate (Recall@K)** with **K = 5**: proportion of queries where the target `document_id` appears in the top-5 results.
- **Mean Reciprocal Rank (MRR):** average of `1/rank` of the target `document_id` across all queries.

### 11.3 Automated Winner Selection & Logging
- Emit a **side-by-side comparison matrix** to **`data/retrieval_eval_results.json`** and **`data/retrieval_eval_results.csv`**, logging Hit Rate and MRR per approach (and per α/k variant for Approach 4).
- **Programmatically determine the best approach** (highest MRR, tie-break on Hit Rate).
- **Write the winner** (approach id + best α/k) back into `src/config.py` (`ACTIVE_RETRIEVAL_APPROACH`, `ACTIVE_ALPHA`, `RRF_K`) so the **production RAG backend uses the winning configuration** automatically.

### 11.4 LLM Evaluation (`evaluate_llm.py`) — A → Q → A′ Framework
- **Setup:** Use an offline ground-truth CSV containing the original **source answer `A`** and the generated **test question `Q`**. Run the RAG generation pipeline to produce **`A′`** for each record.
- **Model Swapping — evaluate two backbones:**
  - **Model A:** OpenAI **`gpt-5.4-mini`**
  - **Model B:** Google **`gemini-2.5-flash`**
  - Both accessed via the `src/llm` abstraction/factory.
- **Secrets:** Load `OPENAI_API_KEY` and `GEMINI_API_KEY`/`GOOGLE_API_KEY` via **python-dotenv** from **`./.env`**.
- **LLM-as-a-Judge:** Pydantic `BaseModel` judge inspecting `(Q, A, A′)`:
  ```python
  class JudgeVerdict(BaseModel):
      verdict: Literal["good", "bad"]     # semantic equivalence of A vs A'
      reasoning: str                       # step-by-step chain-of-thought
  ```
- **Parallelism:** Use **`ThreadPoolExecutor`** to evaluate the full dataset efficiently.
- **Comparative analysis — aggregate per model:**
  - **Accuracy Score:** % of answers classified `good` vs `bad`.
  - **Execution Cost:** total token cost per full evaluation run.
  - **Latency:** average generation time per query.
- **Qualitative failure analysis** on `bad` cases → identify root cause (missing retrieval context vs. model hallucination).
- **Winner selection logic:** explicit code that selects and outputs the winning model based on **accuracy, cost efficiency, and reliability**.

---

## 12. Monitoring & User Feedback (`src/db/monitoring_store.py`, `src/rag/`)

### 12.1 Data Capture
- Instrument the backend to **intercept every LLM call** and capture: **prompt tokens, completion tokens, total tokens, latency (response time), estimated cost (USD)**.
- Persist each conversation into the `conversations` table (§5.3) with a **timezone-aware** timestamp.

### 12.2 Dual Feedback Mechanism
- **Human feedback (`source="user"`):** Streamlit **"+1"** and **"-1"** buttons write `+1` / `-1` to `feedback`, linked by `conversation_id`.
- **Built-in LLM judge (`source="judge"`):** §10.2 relevance verdict saved to `feedback` with `label` + `explanation`.

---

## 13. Streamlit UI (`src/app/`)

### 13.1 Layout
- Single page, **two distinct vertical sections**:
  1. **Q&A interface at the top.**
  2. **Monitoring dashboard directly below it.**

### 13.2 Q&A Panel (`qa_panel.py`)
- **`st.text_input`** to capture the query.
- **`st.button`** to submit and initiate the RAG process.
- **`st.spinner`** for loading feedback while the backend LLM processes.
- **`st.write`** to render the generated answer **alongside execution metrics** (tokens, latency, cost).
- Interactive **"+1" (👍)** and **"-1" (👎)** feedback buttons.

### 13.3 State Management
- Use **`st.session_state`** to store the **`conversation_id`**, persisting it across app reruns so feedback-button clicks link to the correct conversation.

### 13.4 Monitoring Dashboard (`dashboard.py`) — EXACTLY 5 items
1. **Summary Metrics (KPIs):** `st.columns` + `st.metric` for **Total Conversations, Average Response Time, Total Cost, Average Tokens**.
2. **Cost Over Time:** `st.line_chart` of LLM call cost across recent timestamps.
3. **Response Time Over Time:** `st.line_chart` of latency across recent timestamps.
4. **Judge Relevance Distribution:** `st.bar_chart` of aggregate counts of judge classifications (`RELEVANT` / `PARTLY_RELEVANT` / `NON_RELEVANT`).
5. **User Feedback Comparison:** visual split of total **👍 up** vs **👎 down** counts.

> Do not add extra charts. The dashboard MUST contain exactly these five.

---

## 14. Containerization & Task Runner

### 14.1 `docker-compose.yml`
- Orchestrate the **entire system** through a **single** compose file: Streamlit UI, knowledge base, ingestion, monitoring dashboard, and logging databases.
- Mount `./data` and `./models` as volumes so SQLite files and ONNX exports persist.
- Pass secrets via env-file (`./.env`).
- Expose the Streamlit port (e.g., `8501`).

### 14.2 `Makefile` (mandatory targets, minimum set)
| Target | Action |
|---|---|
| `make build` | Build Docker image(s). |
| `make export-models` | Export both HF models to ONNX. |
| `make ingest` | Run the dlt ingestion pipeline over `/data/raw`. |
| `make ground-truth` | Generate `data/ground_truth.csv`. |
| `make eval-retrieval` | Run `evaluate_retrieval.py` + write winner to `config.py`. |
| `make eval-llm` | Run `evaluate_llm.py` (model swap comparison). |
| `make up` | `docker-compose up` (full stack). |
| `make down` | `docker-compose down`. |

> Goal: a peer reviewer runs pipeline stages **without memorizing Python or Docker commands**.

---

## 15. Documentation & Reproducibility

### 15.1 `README.md` (written for **non-experts** with zero project context) MUST:
- Explain the **problem, the data, and the flow** in plain language.
- **Explicitly map how each evaluation criterion is met** (retrieval approaches, metrics, LLM-as-judge, model swap).
- Include **placeholders for screenshots**: UI, monitoring dashboard, and example answers.
- Provide clear instructions for **setup, dependencies, configuration, and environment variables** (`OPENAI_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`).
- Show **example inputs/outputs** (sample query → sample answer + metrics).

### 15.2 Reproducibility
- **Pin all dependency versions** explicitly (`requirements.txt` with `==`, or `Pipfile` + lock).
- If documentation grows too long, **split logically** into **`docs/setup.md`** and **`docs/usage.md`**.

### 15.3 Dataset Accessibility
- README MUST include a **direct link to a public Google Drive folder or GitHub Release** where the reviewer downloads the raw PDF dataset into **`/data/raw`**. (Insert a clearly marked placeholder link for the maintainer to fill.)

### 15.4 Cloud Deployment (Bonus Points Section)
- README MUST include a dedicated section detailing how to deploy the `docker-compose` stack to a **standard cloud VM (e.g., AWS EC2 or DigitalOcean Droplet)** — provisioning, installing Docker + Compose, copying the repo, setting `.env`, opening the Streamlit port, and running `make up` — explicitly to **secure the 2 cloud-deployment bonus points**.

---

## 16. Requirements Traceability Matrix

Every implementation MUST satisfy each row. This is the acceptance checklist.

| # | Requirement | Spec Section | Key Artifact(s) |
|---|---|---|---|
| 1 | Stage 0 query rewriting (LLM) before retrieval | §9.1 | `retrieval/query_rewriter.py` |
| 2 | Stage 1 hybrid: SQLite + `sqlite-vec`/`sqlite-vss` | §5.1, §9.2 | `db/knowledge_store.py`, `retrieval/hybrid_search.py` |
| 3 | FTS5 BM25 lexical + cosine vector search | §9.2 | `hybrid_search.py` |
| 4 | Weighted fusion `α·vec + (1-α)·kw` | §9.2 | `hybrid_search.py` |
| 5 | Embedding model `multi-qa-MiniLM-L6-cos-v1` in ONNX | §7.1–7.2 | `models_onnx/embedder.py` |
| 6 | Stage 2 cross-encoder `ms-marco-MiniLM-L-6-v2` in ONNX, sorted desc | §9.3 | `retrieval/reranker_stage.py` |
| 7 | `master_table` with exact 6 columns; `id` PK | §5.1 | `db/knowledge_store.py` |
| 8 | `id` required for ground-truth methodology (linked URL) | §5.1 | comment + README |
| 9 | Future-proof FK-linkable extension tables | §5.2 | schema + comments |
| 10 | Streamlit UI: Q&A top, dashboard below | §13.1 | `app/streamlit_app.py` |
| 11 | `st.text_input`, `st.button`, `st.spinner`, `st.write` | §13.2 | `app/qa_panel.py` |
| 12 | +1 / -1 feedback buttons | §13.2, §12.2 | `qa_panel.py`, `monitoring_store.py` |
| 13 | `st.session_state` stores `conversation_id` | §13.3 | `streamlit_app.py` |
| 14 | Ingestion uses **dlt** (no standalone script) | §8.1 | `ingestion/pipeline.py` |
| 15 | Source `/data/raw`, **first page only** | §8.2–8.3 | `ingestion/pdf_extractor.py` |
| 16 | Adapt `Skills/datasheet-1.0.0/SKILL.md` for extraction | §8.3 | `pdf_extractor.py` |
| 17 | Map 6 fields; 4–6 → `search_text` → `search_vector` | §8.4 | `resources.py`, `embedder.py` |
| 18 | Graceful handling of missing sections | §8.5 | `pdf_extractor.py` |
| 19 | `generate_ground_truth.py`, `Questions` schema, ~5 Qs/record | §11.1 | `evaluation/generate_ground_truth.py` |
| 20 | `data/ground_truth.csv` with `question`, `document_id` | §11.1 | CSV output |
| 21 | 4 retrieval approaches compared | §11.2 | `evaluate_retrieval.py` |
| 22 | Hit Rate (Recall@5) + MRR | §11.2 | `evaluate_retrieval.py` |
| 23 | Results JSON/CSV + programmatic winner → `config.py` | §11.3 | results files, `config.py` |
| 24 | A→Q→A′ LLM eval; two backbones swap | §11.4 | `evaluate_llm.py`, `llm/factory.py` |
| 25 | Models: `gpt-5.4-mini` + `gemini-2.5-flash` | §6.2, §11.4 | `llm/openai_client.py`, `llm/gemini_client.py` |
| 26 | Keys via python-dotenv from `./.env` | §4.1, §11.4 | `config.py`, `.env.example` |
| 27 | LLM-as-judge `verdict` + `reasoning` (Pydantic) | §11.4 | `evaluate_llm.py` |
| 28 | `ThreadPoolExecutor` batch eval | §11.4 | `evaluate_llm.py` |
| 29 | Accuracy, cost, latency + failure analysis + winner logic | §11.4 | `evaluate_llm.py` |
| 30 | Capture tokens, latency, cost per LLM call | §12.1 | `rag/generator.py`, `monitoring_store.py` |
| 31 | Monitoring in SQLite: `conversations` + `feedback` (FK) | §5.3 | `monitoring_store.py` |
| 32 | Dual feedback: user (+1/-1) + judge (RELEVANT/PARTLY/NON) | §12.2, §10.2 | `qa_panel.py`, `rag/judge.py` |
| 33 | Dashboard: exactly 5 charts/metrics | §13.4 | `app/dashboard.py` |
| 34 | Single `docker-compose.yml` orchestrating all | §14.1 | `docker-compose.yml` |
| 35 | Makefile: `make ingest`, `make eval-retrieval`, `make up`, … | §14.2 | `Makefile` |
| 36 | Non-expert README (problem/data/flow/eval/screenshots/examples) | §15.1 | `README.md` |
| 37 | Pinned dependency versions | §15.2 | `requirements.txt` |
| 38 | Split docs if long (`setup.md`, `usage.md`) | §15.2 | `docs/` |
| 39 | Dataset link (Google Drive / GitHub Release) → `/data/raw` | §15.3 | `README.md` |
| 40 | Cloud deployment section (EC2 / Droplet) for bonus points | §15.4 | `README.md` |

---

**End of Specification.** The implementation agent MUST treat every named library, model, filename, table, column, formula, and metric above as a hard requirement and MUST satisfy all 40 rows of the traceability matrix in §16.