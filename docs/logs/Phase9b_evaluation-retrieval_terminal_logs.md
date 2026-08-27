# Terminal Execution Log — `src/evaluation/evaluate_retrieval.py` Generation (Phase 9b)

This log records the terminal activity, tool usage, and outcomes for the session that:
1. Read `SPEC.MD` §11.2/§11.3 (Retrieval Evaluation, Automated Winner Selection) plus `src/config.py`, `src/retrieval/hybrid_search.py`, `src/retrieval/reranker_stage.py`, and `src/evaluation/generate_ground_truth.py` (as the established atomic-write/CLI-entrypoint precedent) before writing any code.
2. Implemented `src/evaluation/evaluate_retrieval.py` (`evaluate_retrieval() -> dict`): 4 retrieval approaches (lexical, dense vector, hybrid-RRF, hybrid+rerank with an alpha sweep 0.0→1.0), Hit Rate@5/MRR metrics, side-by-side JSON/CSV comparison output, and a byte-exact, atomic winner-writeback into `src/config.py`'s `ACTIVE_RETRIEVAL_APPROACH`/`ACTIVE_ALPHA`/`RRF_K` assignment lines.
3. Found and fixed a real, pre-existing integration bug in `src/retrieval/pipeline.py` (the `APPROACH_HYBRID` production branch was using weighted fusion instead of the RRF fusion spec.md §9.2 mandates for it) while cross-checking the new eval module against its only production consumer.
4. Statically verified both files (`mcp_pylance_mcp_s_pylanceFileSyntaxErrors`, `get_errors`) and ran a multi-section runtime smoke test in a throwaway venv, which caught and led to fixing a second real bug — this one inside `evaluate_retrieval.py` itself (`_replace_config_source()` misused a `dict[str, str]` as if its values were compiled regex patterns) — that **both static-analysis tools had missed**.
5. Updated `docs/PROJECT_NOTES.md` and `/memories/repo/project-notes.md` (plus `/memories/debugging.md` with the reinforced tooling lesson) with the build notes.
6. Did a follow-up, request-driven static-only re-review (Turn 2) that found no further issues.

---

## Summary

All commands below were executed via `run_in_terminal` (PowerShell), all in **Turn 1** (the initial build). **Turn 2** (the user's "review the code" follow-up request) executed **zero terminal commands** — it was a pure static re-review (file re-reads, `grep_search`, `mcp_pylance_mcp_s_pylanceFileSyntaxErrors`, `get_errors`). One throwaway virtual environment was created and destroyed for the runtime smoke test, installed with only the packages needed to import `evaluate_retrieval.py`'s dependency chain (`python-dotenv`, `sqlite-vec`, `numpy`, `onnxruntime`, `transformers` — no `openai`/`google-genai`/`pydantic`/`tenacity` were needed, since this module never imports `src.llm`). Commands, stdout, and stderr are reproduced verbatim below in execution order.

---

## Part 0 — Non-terminal tool activity (Turn 1: context, build, bug fixes, smoke-test authoring, docs)

| # | Tool | Target | Purpose |
|---|---|---|---|
| 1 | `memory` (`view`) + `read_file` (parallel) | `/memories/repo/project-notes.md`; `SPEC.MD` (1-40) | Load established conventions; read the spec's overview/data-flow section. |
| 2 | `grep_search` + `read_file` (parallel) | `SPEC.MD` for `## 11\.\|§11\|Evaluation`; `src/config.py` (1-200) | Locate every §11-relevant reference (50 matches across `SPEC.MD` and `src/retrieval/SPEC.MD`); confirm every existing config constant to reuse. |
| 3 | `read_file` | `SPEC.MD` (300-400) | Read §9.1-9.3 (retrieval stages), §10, and §11.1-11.4 verbatim. |
| 4 | `read_file` | `src/retrieval/hybrid_search.py` (1-400, full file) | Study `Document`, `lexical_search`/`vector_search`/`hybrid_search`/`fuse_weighted`/`fuse_rrf` exact signatures and normalization/fusion behavior. |
| 5 | `read_file` ×2 (parallel) | `src/retrieval/reranker_stage.py` (1-100); `src/evaluation/generate_ground_truth.py` (1-250) | Study `rerank()`'s signature; study the atomic tempfile+`os.replace` write pattern and `__main__` entrypoint style to mirror. |
| 6 | `create_file` | `src/evaluation/evaluate_retrieval.py` | Write the full module (first draft): 4 approaches, Hit Rate/MRR metrics, JSON/CSV writers, `config.py` line-based rewrite, `evaluate_retrieval()`, `__main__`. |
| 7 | `tool_search` | `"pylance file syntax errors checker"` | Load the deferred Pylance syntax-check tool. |
| 8 | `mcp_pylance_mcp_s_pylanceFileSyntaxErrors` + `get_errors` (parallel) | `evaluate_retrieval.py` | Both clean. |
| 9 | `read_file` ×2 | `evaluate_retrieval.py` (1-400, then 395-430) | Full self-review re-read of the just-written file. |
| 10 | `read_file` | `src/retrieval/pipeline.py` (1-120) | Cross-checked the new eval module's Approach 3 (RRF) against its only production consumer — **found the `APPROACH_HYBRID` branch was using weighted fusion, not RRF**. |
| 11 | `replace_string_in_file` | `src/retrieval/pipeline.py` | Fixed: `APPROACH_HYBRID` branch now calls `hybrid_search(rewritten_query, use_rrf=True)`. |
| 12 | `mcp_pylance_mcp_s_pylanceFileSyntaxErrors` + `get_errors` (parallel) | `pipeline.py` | Both clean after the fix. |
| 13 | `read_file` ×2 (parallel) | `src/db/knowledge_store.py` (1-80); `grep_search` for `def get_connection\|def connect\|def init_db` | Confirm `connect()`/`init_db()` signatures for smoke-test DB seeding. |
| 14 | `read_file` | `src/db/knowledge_store.py` (80-200) | Read the FTS5/vec0 trigger DDL to understand how `master_vec`/`master_fts` get auto-populated from `master_table` inserts. |
| 15 | `create_file` | `%TEMP%\evr_smoke_test.py` (throwaway) | Wrote a 4-section smoke test: (A) metric math on synthetic known-rank data, (B) `config.py` rewrite byte-exactness + simulated `os.replace` crash safety, (C) full `evaluate_retrieval()` orchestration against monkeypatched search functions with a hand-computed 3-question ground truth, (D) missing-`ground_truth.csv` graceful handling. |
| 16 | `get_errors` | `evaluate_retrieval.py` | Re-confirmed static analysis reported **no errors** even with the (not-yet-found) `_replace_config_source` bug present — noted for the tooling-limits lesson. |
| 17 | `replace_string_in_file` | `evaluate_retrieval.py` | Fixed `_replace_config_source()`'s pattern lookup (see Command 8 below). |
| 18 | `replace_string_in_file` ×2 | `%TEMP%\evr_smoke_test.py` | Fixed two test-script assumption bugs surfaced by re-running the smoke test (see Commands 9-10 below) — not module bugs. |
| 19 | `mcp_pylance_mcp_s_pylanceFileSyntaxErrors` + `get_errors` (parallel, final) | `evaluate_retrieval.py`, `pipeline.py` | Both clean after all fixes. |
| 20 | `read_file` ×2 (parallel) | `docs/PROJECT_NOTES.md` (1-50, then 1040-1080) | Located the file's existing structure/insertion point. |
| 21 | `multi_replace_string_in_file` | `docs/PROJECT_NOTES.md` (append); no-op guard on `generate_ground_truth.py` | Appended the new build-notes entry; the second (`generate_ground_truth.py`) replacement was a deliberately-never-matching placeholder to guarantee that file was never touched. |
| 22 | `memory` (`str_replace`) | `/memories/repo/project-notes.md` | Mirrored the same build-notes entry into repo memory. |
| 23 | `memory` (`str_replace`) | `/memories/debugging.md` | Added the reinforced lesson: `get_errors`/`pylanceFileSyntaxErrors` can miss real logic bugs (not just syntax), even with inferrable concrete types — always runtime-smoke-test. |

---

## Part 1 — Terminal commands (Turn 1)

### Command 1 — Check `config.py`'s line-ending convention (LF vs CRLF)

```powershell
py -c "data = open(r'c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\src\config.py','rb').read(); print('CRLF count', data.count(b'\r\n')); print('LF count', data.count(b'\n')); print('bare CR', data.count(b'\r') - data.count(b'\r\n'))"
```

**Output:**

```
CRLF count 96
LF count 96
bare CR 0
```

**Purpose:** Confirmed `config.py` uses CRLF line endings throughout (every `\n` is part of a `\r\n` pair, zero bare `\r`/`\n`), which determined the design of `_write_winner_to_config()`'s byte-exact rewrite (`open(..., newline="")` on both read and write, so Python's universal-newline translation never silently converts or double-corrupts the existing CRLF endings).

---

### Command 2 — Verify `csv` module's `None` serialization behavior

```powershell
py -c "import csv,io; buf=io.StringIO(); w=csv.writer(buf); w.writerow([None, 1, 'x']); print(repr(buf.getvalue()))"
```

**Output:**

```
',1,x\r\n'
```

**Purpose:** Confirmed `csv.writer` serializes `None` as an empty string (not the literal text `"None"`), validating that `_write_results_csv()`'s `alpha`/`rrf_k` fields (which are `None` for approaches that don't use that parameter) would render as blank CSV cells, not junk text.

---

### Command 3 — Create a throwaway venv and install the smoke-test dependency set

```powershell
$venv = Join-Path $env:TEMP ("eval_retrieval_venv_" + [guid]::NewGuid().ToString("N")); py -m venv $venv; & "$venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check python-dotenv==1.2.3 sqlite-vec==0.1.9 numpy==2.3.5 onnxruntime==1.29.0 transformers==4.57.6; Write-Output "VENV=$venv"
```

**Output:**

```
(Command produced no output)
```

---

### Command 4 — Check the venv path and Python version

```powershell
Write-Output "VENV=$venv"; & "$venv\Scripts\python.exe" --version
```

**Output:**

```
+ ~~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (Write-Output:String) [], Comma 
   ndNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException
 
Python 3.13.5
```

**Diagnosis:** The `Write-Output : CommandNotFoundException` portion is a terminal-capture/echo artifact (the persistent PowerShell session's prior state briefly rendered a stale/partial error banner for a cmdlet that unquestionably exists), not a real fault — the `python --version` invocation on the same line still executed and returned `Python 3.13.5` correctly. Re-verified immediately after with a plain sanity command (Command 5).

---

### Command 5 — Sanity-check the terminal is responsive

```powershell
echo test123
```

**Output:**

```
test123
```

---

### Command 6 — Re-confirm the `$venv` variable survived in this persistent session

```powershell
"VENV=$venv"
```

**Output:**

```
VENV=C:\Users\Tanj\AppData\Local\Temp\eval_retrieval_venv_49bd89c9ffd44488ba438ced12198ae1
```

---

### Command 7 — Verify the required packages actually installed

```powershell
& "$venv\Scripts\python.exe" -c "import dotenv, sqlite_vec, numpy, onnxruntime, transformers; print('ok')"
```

**Output:**

```
None of PyTorch, TensorFlow >= 2.0, or Flax have been found. Models won't be ava
ilable and only tokenizers, configuration and file/data utilities can be used.
ok
```

**Diagnosis:** The PyTorch/TensorFlow/Flax warning is benign — `transformers` is only used here for its `AutoTokenizer` (via `src.models_onnx.embedder`/`reranker`'s lazy-loaded ONNX sessions), not any deep-learning framework backend. All 5 packages imported successfully (`ok`).

---

### Command 8 — Run the smoke test (1st run) — real bug #1 found

```powershell
& "$venv\Scripts\python.exe" "C:\Users\Tanj\AppData\Local\Temp\evr_smoke_test.py"
```

**Output:**

```
None of PyTorch, TensorFlow >= 2.0, or Flax have been found. Models won't be ava
ilable and only tokenizers, configuration and file/data utilities can be used.
SECTION A (metric math) OK
Traceback (most recent call last):
  File "C:\Users\Tanj\AppData\Local\Temp\evr_smoke_test.py", line 64, in <module
>
    evr._write_winner_to_config(approach="dense_vector", alpha=0.3, rrf_k=60)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\src\evaluation\eval
uate_retrieval.py", line 299, in _write_winner_to_config
    updated = _replace_config_source(
        original,
    ...<4 lines>...
        },
    )
  File "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\src\evaluation\eval
uate_retrieval.py", line 266, in _replace_config_source
    match = pattern.match(body)
            ^^^^^^^^^^^^^
AttributeError: 'str' object has no attribute 'match'
```

**Diagnosis:** Real bug in `evaluate_retrieval.py` itself. `_replace_config_source()`'s inner loop did `for key, pattern in list(remaining.items())`, but `remaining` is `dict(new_values)` — a `dict[str, str]` mapping key → *replacement value*, not key → compiled `re.Pattern`. Calling `.match()` on the string value raised `AttributeError` on the very first invocation. Confirmed via a follow-up `get_errors` call that **both `get_errors` and the earlier `pylanceFileSyntaxErrors` pass had reported this file as fully clean** — this bug was invisible to static analysis and only surfaced by actually running the code. Fixed by looking up the real pattern via `_ASSIGNMENT_PATTERNS[key]` and popping the replacement value separately.

---

### Command 9 — Re-run after the fix (2nd run) — test-script assumption bug (not a module bug)

```powershell
& "$venv\Scripts\python.exe" "C:\Users\Tanj\AppData\Local\Temp\evr_smoke_test.py"
```

**Output:**

```
None of PyTorch, TensorFlow >= 2.0, or Flax have been found. Models won't be ava
ilable and only tokenizers, configuration and file/data utilities can be used.
SECTION A (metric math) OK
Changed line indices: [84, 85]
  [84] b'ACTIVE_RETRIEVAL_APPROACH: str = APPROACH_HYBRID_RERANK' -> b'ACTIVE_RE
TRIEVAL_APPROACH: str = APPROACH_VECTOR'
  [85] b'ACTIVE_ALPHA: float = ALPHA' -> b'ACTIVE_ALPHA: float = 0.3'
Traceback (most recent call last):
  File "C:\Users\Tanj\AppData\Local\Temp\evr_smoke_test.py", line 76, in <module
>
    assert len(diffs) == 3, f"expected exactly 3 changed lines, got {len(diffs)
}"
           ^^^^^^^^^^^^^^^
AssertionError: expected exactly 3 changed lines, got 2
```

**Diagnosis:** Not a module bug — the smoke-test script itself assumed the `RRF_K` line would always change, but the test called `_write_winner_to_config(..., rrf_k=60)` with the *same* value `config.py` already had (`60`), so that line was correctly rewritten to byte-identical content (0 visible diff). Fixed the test script to pass `rrf_k=45` (a genuinely different value) so all 3 target lines actually change.

---

### Command 10 — Re-run after test fix #1 (3rd run) — second test-script assumption bug

```powershell
& "$venv\Scripts\python.exe" "C:\Users\Tanj\AppData\Local\Temp\evr_smoke_test.py"
```

**Output:**

```
None of PyTorch, TensorFlow >= 2.0, or Flax have been found. Models won't be ava
ilable and only tokenizers, configuration and file/data utilities can be used.
SECTION A (metric math) OK
Changed line indices: [67, 84, 85]
  [67] b'RRF_K: int = 60  # Reciprocal Rank Fusion constant' -> b'RRF_K: int = 4
5  # Reciprocal Rank Fusion constant'
  [84] b'ACTIVE_RETRIEVAL_APPROACH: str = APPROACH_HYBRID_RERANK' -> b'ACTIVE_RE
TRIEVAL_APPROACH: str = APPROACH_VECTOR'
  [85] b'ACTIVE_ALPHA: float = ALPHA' -> b'ACTIVE_ALPHA: float = 0.3'
Traceback (most recent call last):
  File "C:\Users\Tanj\AppData\Local\Temp\evr_smoke_test.py", line 77, in <module
>
    assert new_lines[diffs[0]] == b"ACTIVE_RETRIEVAL_APPROACH: str = APPROACH_VE
CTOR"
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
^^^^^
AssertionError
```

**Diagnosis:** Again a test-script bug, not a module bug — `RRF_K` (line 67) sorts *before* `ACTIVE_RETRIEVAL_APPROACH`/`ACTIVE_ALPHA` (lines 84-85) in `config.py`'s actual line order, but the test's assertion assumed `diffs[0]` was always the `ACTIVE_RETRIEVAL_APPROACH` line. Fixed the test to compare changed-line *content* as a set, independent of line position.

---

### Command 11 — Re-run after test fix #2 (4th run) — all sections pass

```powershell
& "$venv\Scripts\python.exe" "C:\Users\Tanj\AppData\Local\Temp\evr_smoke_test.py"
```

**Output:**

```
None of PyTorch, TensorFlow >= 2.0, or Flax have been found. Models won't be ava
ilable and only tokenizers, configuration and file/data utilities can be used.
SECTION A (metric math) OK
Changed line indices: [67, 84, 85]
  [67] b'RRF_K: int = 60  # Reciprocal Rank Fusion constant' -> b'RRF_K: int = 4
5  # Reciprocal Rank Fusion constant'
  [84] b'ACTIVE_RETRIEVAL_APPROACH: str = APPROACH_HYBRID_RERANK' -> b'ACTIVE_RE
TRIEVAL_APPROACH: str = APPROACH_VECTOR'
  [85] b'ACTIVE_ALPHA: float = ALPHA' -> b'ACTIVE_ALPHA: float = 0.3'
SECTION B1 (happy path, byte-exact) OK
SECTION B2 (crash safety) OK
SECTION C (metrics/winner selection) OK -> dense_vector dense_vector
SECTION C (JSON/CSV outputs) OK
SECTION C (config3.py winner write) OK
Real config.py untouched: OK
Ground-truth CSV not found at C:\Users\Tanj\AppData\Local\Temp\evr_config_test_w
rvz1rgc\does_not_exist.csv; skipping retrieval evaluation.
No ground-truth data available; retrieval evaluation was not run.
SECTION D (missing ground_truth.csv) OK
ALL SECTIONS PASSED
```

**Result:** All 4 sections passed:
- **A** — metric math on synthetic known-rank data (hit@1, hit@3 partial rank `1/3`, and a miss) matched hand-computed Hit Rate/MRR exactly.
- **B1** — `config.py` rewrite happy path: exactly 3 lines changed, byte-identical everywhere else, correct new content for all 3 (incl. the preserved `RRF_K` trailing comment).
- **B2** — simulated `os.replace` failure: target file byte-identical to before the call, zero leftover `.config_*` temp files.
- **C** — full `evaluate_retrieval()` orchestration against monkeypatched `lexical_search`/`vector_search`/`hybrid_search`/`rerank` and a deterministic 3-question ground truth: all 14 rows' Hit Rate/MRR matched hand-computed expected values, JSON/CSV outputs contained all 14 rows with exactly one `is_winner=True`, the winner was written correctly to a fake `config.py` copy, and **the real `src/config.py` was confirmed byte-identical before/after the entire test run**.
- **D** — missing `ground_truth.csv` → `{"results": [], "winner": None}` returned, no JSON/CSV output files created.

---

### Command 12 — Clean up the venv, smoke-test script, and temp artifacts

```powershell
Remove-Item -Recurse -Force $venv -ErrorAction SilentlyContinue; Remove-Item -Force "C:\Users\Tanj\AppData\Local\Temp\evr_smoke_test.py" -ErrorAction SilentlyContinue; Get-ChildItem $env:TEMP -Filter "evr_*" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "cleanup done"
```

**Output:**

```
cleanup done
```

---

### Command 13 — Verify cleanup left no residue

```powershell
Test-Path $venv; Get-ChildItem $env:TEMP -Filter "evr_*"; Test-Path "C:\Users\Tanj\AppData\Local\Temp\evr_smoke_test.py"
```

**Output:**

```
False
False
```

**Result:** Venv path gone (`False`), no `evr_*`-named leftovers in `%TEMP%` (empty `Get-ChildItem` result, no line printed for it), and the smoke-test script itself gone (`False`). Confirms full hygiene per the temp-file cleanup lesson in repo memory.

---

### Command 14 — Confirm only the intended files changed (git status/diff)

```powershell
cd c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code; git status --porcelain; git diff --stat
```

**Output:**

```
Note: The tool simplified the command to `git status --porcelain; git diff --stat` (terminal ID=e12fad4c-3b3a-4caa-a408-fac843411899). This is the output of running that command instead:
 M src/retrieval/pipeline.py
?? src/evaluation/evaluate_retrieval.py
 src/retrieval/pipeline.py | 12 ++++++++----
 1 file changed, 8 insertions(+), 4 deletions(-)
```

**Result:** Confirmed only the two intended files changed — `src/retrieval/pipeline.py` (the RRF-branch bug fix, 8 insertions/4 deletions) and the new, untracked `src/evaluation/evaluate_retrieval.py`. `src/config.py` did **not** appear in the diff, confirming the real file was never touched during development/smoke-testing (it is only ever rewritten at actual `make eval-retrieval` runtime).

---

## Part 2 — Turn 2 (user-requested code review) — no terminal commands

The user's second request in this session ("Can you please review the code you produced for any potential bug and issues?") was handled entirely via static re-review — **zero `run_in_terminal` calls were made in this turn**. Tool activity was: re-reading `evaluate_retrieval.py` (full) and the `pipeline.py` edit, a targeted `grep_search` for debug leftovers (`print(`/`TODO`/`FIXME`/`pdb`/`breakpoint`, none found) and for any other occurrence of `ACTIVE_RETRIEVAL_APPROACH`/`ACTIVE_ALPHA`/`RRF_K` in `config.py` (confirmed exactly one occurrence of each, no false-match risk for the line-based rewrite regexes), and a final `mcp_pylance_mcp_s_pylanceFileSyntaxErrors` + `get_errors` re-check on both files (both clean). No new bugs were found in this pass; the two bugs already fixed in Turn 1 were the only real issues.

---

## Part 3 — Turn 3 (this documentation request) — no terminal commands

| # | Tool | Target | Purpose |
|---|---|---|---|
| 1 | `list_dir` + `read_file` (parallel) | `docs/logs/`; `PHASE9a_groundtruth_terminal_logs.md` | Confirm `docs/logs/` already exists; study the established terminal-log formatting convention. |
| 2 | `read_file` | `PHASE9a_groundtruth_CONVERSATION_TRANSCRIPT.md` | Study the established conversation-transcript formatting convention. |
| 3 | `create_file` | `docs/logs/Phase9b_evaluation-retrieval_terminal_logs.md` | This file. |
| 4 | `create_file` | `docs/logs/Phase9b_evaluation-retrieval_CONVERSATION_TRANSCRIPT.md` | The full chat transcript (see sibling file). |

No `run_in_terminal` calls were needed for this documentation turn.

---

## Final state

- `src/evaluation/evaluate_retrieval.py` — new module: `evaluate_retrieval() -> dict`, `__main__` entrypoint for `make eval-retrieval`. 4 retrieval approaches (lexical, dense vector, hybrid-RRF, hybrid+rerank alpha-swept 0.0→1.0), Hit Rate@5/MRR metrics, JSON/CSV side-by-side comparison output, atomic byte-exact `config.py` winner rewrite.
- `src/retrieval/pipeline.py` — one-branch fix: `APPROACH_HYBRID` now uses RRF fusion (`hybrid_search(..., use_rrf=True)`), matching spec.md §9.2's explicit intent and this new module's own Approach 3.
- `pylanceFileSyntaxErrors` + `get_errors`: clean on both files, confirmed both before *and* after every fix (including the one bug static analysis alone had missed).
- `requirements.txt`: no new entries needed (stdlib `csv`/`json`/`os`/`re`/`tempfile`/`pathlib`/`collections.abc.Callable` plus existing internal `src.*` imports).
- `docs/PROJECT_NOTES.md` and `/memories/repo/project-notes.md`: both updated with the full build/bug-fix/smoke-test summary; `/memories/debugging.md` updated with the reinforced "static analysis can miss real logic bugs" lesson.
- No leftover temp files, venvs, or throwaway smoke-test scripts remain in the workspace or `%TEMP%` after the session (verified via `Test-Path`).
- `git status --porcelain`/`git diff --stat` confirmed only the two intended files changed; `src/config.py` untouched in the working tree.
