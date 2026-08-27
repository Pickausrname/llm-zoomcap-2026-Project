# Terminal Execution Log — `src/evaluation/evaluate_llm.py` Build & Review (Phase 9c)

This log records **every terminal command executed via `run_in_terminal`** during the session that built and reviewed `src/evaluation/evaluate_llm.py` (spec.md §11.4, LLM Evaluation — A → Q → A′ Framework), across four user turns:

1. **Turn 1 — Build.** Implemented `evaluate_llm.py` (cross-graded A/Q/A′ judge, sequential-per-model/parallel-within-model `ThreadPoolExecutor` batches, skip-and-continue failure handling, qualitative failure-analysis heuristic) plus the sanctioned `src/db/monitoring_store.py` schema extension (`feedback.source` widened to include `"eval_judge"`, new `llm_eval_runs` table + `insert_llm_eval_run()`) and two new `src/config.py` constants. Verified via a throwaway-venv runtime smoke test.
2. **Turn 2 — Follow-up review round.** Found and fixed a real bug: `rag/generator.py`'s `generate_answer()` swallows most LLM-side failures internally and returns a canned fallback answer instead of raising, which `evaluate_llm.py` was not detecting. Fixed by making the fallback sentinel (`GENERATION_FAILURE_MODEL`) public and checking for it explicitly. Verified via a second, focused throwaway-venv smoke test.
3. **Turn 3 — Cross-module static integration review.** Re-read and syntax-checked all 30 `src/` files, verified cross-module wiring/schemas/requirements/`__init__.py`/dead-code, and found (and fixed) one housekeeping issue: a stray byte-identical duplicate of `SPEC.MD` sitting inside `src/retrieval/`.
4. **Turn 4 — This documentation turn.**

All commands below were executed via `run_in_terminal` (PowerShell). Every throwaway virtual environment and temp file/directory created during smoke-testing was deleted again in the same turn (per this repo's temp-file-cleanup hygiene convention) — cleanup commands and their verification are included below.

> **Note on a recurring terminal-capture quirk:** Several commands in Turns 1-2 show a `CommandNotFoundException` referencing the *previous* command's variable/cmdlet name, with no output for the *current* command. This was a benign output-buffering/echo lag in the terminal tool (the visible error text lagged one command behind), not a real PowerShell fault — every case was immediately re-verified with a follow-up command that produced the correct result. This is called out inline at each occurrence rather than re-explained every time.

---

## Part 1 — Turn 1: Building `evaluate_llm.py`

### Command 1 — Create a throwaway venv and upgrade pip

```powershell
$venvPath = Join-Path $env:TEMP ("venv_evalllm_" + [guid]::NewGuid().ToString("N")); py -m venv $venvPath; "$venvPath" | Out-File -FilePath "$env:TEMP\evalllm_venv_path.txt" -Encoding ascii; & "$venvPath\Scripts\python.exe" -m pip install --upgrade pip -q
```

**Output:**

```
(Command produced no output)
```

---

### Command 2 — Install the smoke-test dependency set (first attempt)

```powershell
$venvPath = Get-Content "$env:TEMP\evalllm_venv_path.txt"; & "$venvPath\Scripts\python.exe" -m pip install -q python-dotenv==1.2.3 sqlite-vec==0.1.9 "optimum[onnxruntime]==2.1.0" transformers==4.57.6 onnxruntime==1.29.0 numpy==2.3.5 openai==3.3.1 google-genai==2.19.0 pydantic==2.13.4 tenacity==9.1.4
```

**Output:**

```
$venvPath : The term '$venvPath' is not recognized as the name of a cmdlet,
function, script file, or operable program. Check the spelling of the name, or
if a path was included, verify that the path is correct and try again.
At line:1 char:1
+ $venvPath = Get-Content "$env:TEMP\evalllm_venv_path.txt"; & "$venvP ...
+ ~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: ($venvPath:String) [], CommandN
   otFoundException
    + FullyQualifiedErrorId : CommandNotFoundException
```

**Diagnosis:** `Get-Content` (no `-Raw`) plus immediate `.Trim()`-free interpolation was fragile here; moved to debugging the venv-path file directly (Commands 3-7) before retrying the install.

---

### Command 3 — Debug: read the venv path file

```powershell
Get-Content "$env:TEMP\evalllm_venv_path.txt"
```

**Output:**

```
(Command produced no output)
```

---

### Command 4 — Debug: check the file/venv actually exist

```powershell
Test-Path "$env:TEMP\evalllm_venv_path.txt"; Get-ChildItem $env:TEMP -Filter "venv_evalllm_*" -Directory
```

**Output:**

```
(Command produced no output)
```

---

### Command 5 — Debug: basic terminal sanity check

```powershell
Write-Output "hello"
```

**Output:**

```
hello
```

---

### Command 6 — Debug: confirm the path file exists via an explicit boolean

```powershell
$p = Test-Path "$env:TEMP\evalllm_venv_path.txt"; Write-Output "exists=$p"
```

**Output:**

```
exists=True
```

---

### Command 7 — Debug: read the path file with `-Raw`

```powershell
Get-Content -Raw "$env:TEMP\evalllm_venv_path.txt"
```

**Output:**

```
C:\Users\Tanj\AppData\Local\Temp\venv_evalllm_85b9675f3261463e8b759c300aa3c1b7
```

**Diagnosis:** `-Raw` was the fix — subsequent commands read the venv path via `(Get-Content -Raw ...).Trim()`.

---

### Command 8 — Install the smoke-test dependency set (retry, using `-Raw`)

```powershell
$venvPath = (Get-Content -Raw "$env:TEMP\evalllm_venv_path.txt").Trim(); & "$venvPath\Scripts\python.exe" -m pip install -q python-dotenv==1.2.3 sqlite-vec==0.1.9 "optimum[onnxruntime]==2.1.0" transformers==4.57.6 onnxruntime==1.29.0 numpy==2.3.5 openai==3.3.1 google-genai==2.19.0 pydantic==2.13.4 tenacity==9.1.4
```

**Output:**

```
(Command produced no output)
```

---

### Command 9 — Verify the packages actually installed

```powershell
$venvPath = (Get-Content -Raw "$env:TEMP\evalllm_venv_path.txt").Trim(); & "$venvPath\Scripts\python.exe" -m pip list 2>&1 | Select-String -Pattern "onnxruntime|transformers|openai|google-genai|pydantic|numpy|optimum"
```

**Output:**

```
google-genai       2.19.0
numpy              2.3.5
onnxruntime        1.29.0
openai             3.3.1
optimum            2.1.0
optimum-onnx       0.1.0
pydantic           2.13.4
pydantic_core      2.46.4
transformers       4.57.6
```

---

### Command 10 — Run the smoke test (first invocation, relative path)

```powershell
$venvPath = (Get-Content -Raw "$env:TEMP\evalllm_venv_path.txt").Trim(); Set-Location "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code"; & "$venvPath\Scripts\python.exe" _tmp_smoke_evaluate_llm.py
```

**Output:**

```
(Command produced no output)
```

---

### Command 11 — Run the smoke test (absolute path + exit code)

```powershell
$venvPath = (Get-Content -Raw "$env:TEMP\evalllm_venv_path.txt").Trim(); & "$venvPath\Scripts\python.exe" "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\_tmp_smoke_evaluate_llm.py"; Write-Output "EXITCODE=$LASTEXITCODE"
```

**Output:**

```
$venvPath : The term '$venvPath' is not recognized as the name of a cmdlet,
function, script file, or operable program. Check the spelling of the name, or
if a path was included, verify that the path is correct and try again.
At line:1 char:1
+ $venvPath = (Get-Content -Raw "$env:TEMP\evalllm_venv_path.txt").Tri ...
+ ~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: ($venvPath:String) [], CommandN
   otFoundException
    + FullyQualifiedErrorId : CommandNotFoundException

Skipping ground-truth row: no master_table row for document_id=99
generate_answer failed for model=openai document_id=3 question='What is CE300?'
Traceback (most recent call last):
  File "C:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\src\evaluation\evaluate_llm.py", line 278, in _evaluate_row
    generated = generate_answer(row.question, provider=model)
  File "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\_tmp_smoke_evaluate_llm.py", line 115, in fake_generate_answer
    raise RuntimeError("simulated generation failure")
RuntimeError: simulated generation failure
Judge call (provider=gemini) failed for model=openai document_id=2 conversation_id=06350aca-834d-417c-b548-b44f446a119f
Traceback (most recent call last):
  File "C:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\src\evaluation\evaluate_llm.py", line 299, in _evaluate_row
    parsed, judge_response = judge_llm.structured(
                             ~~~~~~~~~~~~~~~~~~~~^
        prompt, JudgeVerdict, system=_JUDGE_SYSTEM_PROMPT
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\_tmp_smoke_evaluate_llm.py", line 153, in structured
    raise RuntimeError("simulated judge failure")
RuntimeError: simulated judge failure
Ground-truth CSV at C:\Users\Tanj\AppData\Local\Temp\evalllm_smoke_hutd8zbz\ground_truth.csv has no usable rows; skipping LLM evaluation.
No ground-truth data available; LLM evaluation was not run.
Ground-truth CSV not found at C:\Users\Tanj\AppData\Local\Temp\evalllm_smoke_hutd8zbz\does_not_exist.csv; skipping LLM evaluation.
No ground-truth data available; LLM evaluation was not run.
ALL SMOKE TEST ASSERTIONS PASSED
EXITCODE=0
```

**Diagnosis:** The leading `CommandNotFoundException` block is the same lagged-echo artifact from Command 2, not a real failure of *this* command — the actual script ran (its `logger.error` tracebacks for the two deliberately-simulated failures are expected test output, printed to stderr), and the final two lines (`ALL SMOKE TEST ASSERTIONS PASSED`, `EXITCODE=0`) confirm every assertion passed: `document_id=99` correctly skipped, per-model `n_samples`/`n_judged`/`n_failures`/`accuracy`/`avg_latency_seconds`/`total_cost_usd`/`failure_analysis` all matched hand-computed values, cross-grading verified, winner selection verified, JSON/CSV outputs verified, `feedback`/`llm_eval_runs` rows verified, the `source='bogus'` CHECK-constraint violation verified, empty/missing-ground-truth handling verified, and `src/config.py` confirmed byte-identical before/after the run.

---

### Command 12 — Clean up: smoke-test script, venv, and marker file

```powershell
Remove-Item "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\_tmp_smoke_evaluate_llm.py" -Force; $venvPath = (Get-Content -Raw "$env:TEMP\evalllm_venv_path.txt").Trim(); Remove-Item $venvPath -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item "$env:TEMP\evalllm_venv_path.txt" -Force; Get-ChildItem $env:TEMP -Filter "evalllm_smoke_*" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; Write-Output "cleanup done"
```

**Output:**

```
cleanup done
```

---

### Command 13 — Verify cleanup + check git status

```powershell
Get-ChildItem $env:TEMP -Filter "*evalllm*" -ErrorAction SilentlyContinue; Set-Location "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code"; git status --short
```

**Output:**

```
 M docs/PROJECT_NOTES.md
 M src/config.py
 M src/db/monitoring_store.py
 M src/retrieval/pipeline.py
?? docs/logs/Phase9b_evaluation-retrieval_CONVERSATION_TRANSCRIPT.md
?? docs/logs/Phase9b_evaluation-retrieval_terminal_logs.md
?? src/evaluation/evaluate_llm.py
?? src/evaluation/evaluate_retrieval.py
```

**Note:** No leftover `*evalllm*` temp artifacts; `src/retrieval/pipeline.py` shows modified from an *earlier* (Phase 9b) session, not this one.

---

## Part 2 — Turn 2: Follow-up review round (found & fixed a real bug)

### Command 14 — Create a second throwaway venv and install dependencies

```powershell
$venvPath = Join-Path $env:TEMP ("venv_evalllm2_" + [guid]::NewGuid().ToString("N")); py -m venv $venvPath; $venvPath | Out-File -FilePath "$env:TEMP\evalllm_venv_path2.txt" -Encoding ascii -NoNewline; & "$venvPath\Scripts\python.exe" -m pip install -q python-dotenv==1.2.3 sqlite-vec==0.1.9 "optimum[onnxruntime]==2.1.0" transformers==4.57.6 onnxruntime==1.29.0 numpy==2.3.5 openai==3.3.1 google-genai==2.19.0 pydantic==2.13.4 tenacity==9.1.4; Write-Output "install done"
```

**Output:**

```
(No output captured before the tool returned — the command was still completing; verified as successful in Commands 17-18 below.)
```

---

### Command 15 — Debug: basic terminal sanity check

```powershell
Write-Output "check"
```

**Output:**

```
(Command produced no output)
```

---

### Command 16 — Debug: basic terminal sanity check (variable form)

```powershell
$x = "check2"; Write-Output $x
```

**Output:**

```
(Command produced no output)
```

---

### Command 17 — Verify the second venv's marker file exists

```powershell
Test-Path "$env:TEMP\evalllm_venv_path2.txt"
```

**Output:**

```
True
```

---

### Command 18 — Verify the second venv's packages installed

```powershell
$venvPath2 = (Get-Content -Raw "$env:TEMP\evalllm_venv_path2.txt").Trim(); & "$venvPath2\Scripts\python.exe" -m pip list 2>&1 | Select-String -Pattern "onnxruntime|transformers|openai|google-genai|pydantic"
```

**Output:**

```
google-genai       2.19.0
onnxruntime        1.29.0
openai             3.3.1
pydantic           2.13.4
pydantic_core      2.46.4
transformers       4.57.6
```

---

### Command 19 — Run the focused sentinel-detection smoke test (first attempt)

```powershell
$venvPath2 = (Get-Content -Raw "$env:TEMP\evalllm_venv_path2.txt").Trim(); & "$venvPath2\Scripts\python.exe" "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\_tmp_smoke_evaluate_llm2.py"; Write-Output "EXITCODE=$LASTEXITCODE"
```

**Output:**

```
(Command produced no output)
```

---

### Command 20 — Attempt to flush/re-check output

```powershell
Write-Output "flush"
```

**Output:**

```
+ ~~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (Write-Output:String) [], Comma
   ndNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException
```

**Diagnosis:** Same lagged-echo terminal quirk noted at the top of this log — this is stale output from a prior command's buffer, not a real error in `Write-Output` (a builtin cmdlet).

---

### Command 21 — Basic diagnostic to confirm terminal is healthy

```powershell
1+1
```

**Output:**

```
2
```

---

### Command 22 — Re-run the smoke test, capturing output to a variable

```powershell
$venvPath2 = (Get-Content -Raw "$env:TEMP\evalllm_venv_path2.txt").Trim(); & "$venvPath2\Scripts\python.exe" "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\_tmp_smoke_evaluate_llm2.py" 2>&1 | Tee-Object -Variable smokeOut; $smokeOut | Out-String
```

**Output:**

```
(Command produced no output)
```

---

### Command 23 — Print the captured variable

```powershell
$smokeOut | Out-String
```

**Output:**

```
+ ~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: ($smokeOut:String) [], CommandN
   otFoundException
    + FullyQualifiedErrorId : CommandNotFoundException
```

**Diagnosis:** Same terminal-capture lag; abandoned the variable-capture approach in favor of redirecting straight to a file (Command 24).

---

### Command 24 — Redirect all output to a file instead

```powershell
$venvPath2 = (Get-Content -Raw "$env:TEMP\evalllm_venv_path2.txt").Trim(); & "$venvPath2\Scripts\python.exe" "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\_tmp_smoke_evaluate_llm2.py" *> "$env:TEMP\smoke2_output.txt"; Write-Output "DONE=$LASTEXITCODE"
```

**Output:**

```
(Command produced no output)
```

*(A non-terminal `read_file` call on `smoke2_output.txt` at this point showed the file was UTF-16-encoded — PowerShell's default redirect encoding — which is why Commands 25-26 use `Get-Content -Encoding Unicode` to read it back correctly.)*

---

### Command 25 — Read the redirected output file (first attempt)

```powershell
Get-Content "$env:TEMP\smoke2_output.txt" -Encoding Unicode
```

**Output:**

```
+ ~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (Get-Content:String) [], Comman
   dNotFoundException
    + FullyQualifiedErrorId : CommandNotFoundException
```

**Diagnosis:** Same lagged-echo terminal quirk again; retried with an explicit `-Path` parameter.

---

### Command 26 — Read the redirected output file (retry with `-Path`)

```powershell
Get-Content -Path "$env:TEMP\smoke2_output.txt" -Encoding Unicode
```

**Output:**

```
python.exe : generate_answer() returned a generation-failure fallback for
model=openai document_id=1; treating as a row failure.
At line:1 char:76
+ ... t").Trim(); & "$venvPath2\Scripts\python.exe" "c:\Users\Tanj\Document ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (generate_answer... a row failure.
   :String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError

generate_answer() returned a generation-failure fallback for model=gemini
document_id=1; treating as a row failure.
SENTINEL-DETECTION SMOKE TEST PASSED
```

**Diagnosis:** The `logger.warning(...)` calls (going to stderr) were rendered by PowerShell as native-command "errors" — cosmetic only, not real failures. The final line, **`SENTINEL-DETECTION SMOKE TEST PASSED`**, confirms the fix: for both models, a `GENERATION_FAILURE_MODEL` fallback answer was correctly detected and treated as a row failure — the judge LLM was never called (verified via an assertion that raises if it is), `n_failures=1`/`n_judged=0`/`accuracy=0.0`/`avg_latency_seconds=0.0`/`total_cost_usd=0.0` for both models, and zero `feedback` rows were persisted.

---

### Command 27 — Clean up: smoke-test script, output file, venv, marker file, temp dirs

```powershell
Remove-Item "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\_tmp_smoke_evaluate_llm2.py" -Force -ErrorAction SilentlyContinue
Remove-Item "$env:TEMP\smoke2_output.txt" -Force -ErrorAction SilentlyContinue
$venvPath2 = (Get-Content -Raw "$env:TEMP\evalllm_venv_path2.txt").Trim()
Remove-Item $venvPath2 -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$env:TEMP\evalllm_venv_path2.txt" -Force -ErrorAction SilentlyContinue
Get-ChildItem $env:TEMP -Filter "evalllm_smoke2_*" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Output "cleanup2 done"
```

**Output:**

```
PS C:\Users\Tanj\Documents\llmzoomcamp2026\Project\code> Remove-Item "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\_tmp_smoke_evaluate_llm2.py" -Force -ErrorAction SilentlyContinue
PS C:\Users\Tanj\Documents\llmzoomcamp2026\Project\code> Remove-Item "$env:TEMP\smoke2_output.txt" -Force -ErrorAction SilentlyContinue
PS C:\Users\Tanj\Documents\llmzoomcamp2026\Project\code> $venvPath2 = (Get-Content -Raw "$env:TEMP\evalllm_venv_path2.txt").Trim()
PS C:\Users\Tanj\Documents\llmzoomcamp2026\Project\code> Remove-Item $venvPath2 -Recurse -Force -ErrorAction SilentlyContinue
PS C:\Users\Tanj\Documents\llmzoomcamp2026\Project\code> Remove-Item "$env:TEMP\evalllm_venv_path2.txt" -Force -ErrorAction SilentlyContinue
PS C:\Users\Tanj\Documents\llmzoomcamp2026\Project\code> Get-ChildItem $env:TEMP -Filter "evalllm_smoke2_*" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
PS C:\Users\Tanj\Documents\llmzoomcamp2026\Project\code> Write-Output "cleanup2 done"
cleanup2 done
```

---

### Command 28 — Final verification: no leftover temp artifacts + git status

```powershell
Get-ChildItem $env:TEMP -Filter "*evalllm*" -ErrorAction SilentlyContinue; git status --short
```

**Output:**

```
 M docs/PROJECT_NOTES.md
 M src/config.py
 M src/db/monitoring_store.py
 M src/rag/generator.py
 M src/retrieval/pipeline.py
?? docs/logs/Phase9b_evaluation-retrieval_CONVERSATION_TRANSCRIPT.md
?? docs/logs/Phase9b_evaluation-retrieval_terminal_logs.md
?? src/evaluation/evaluate_llm.py
?? src/evaluation/evaluate_retrieval.py
```

**Note:** `src/rag/generator.py` now correctly shows as modified — the `GENERATION_FAILURE_MODEL` sentinel rename made in this turn. No leftover `*evalllm*` temp files.

---

## Part 3 — Turn 3: Cross-module static integration review

### Command 29 — Compare `SPEC.MD` vs. `src/retrieval/SPEC.MD` by hash, and check git history

```powershell
Set-Location "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code"; $a = Get-FileHash "SPEC.MD"; $b = Get-FileHash "src\retrieval\SPEC.MD"; Write-Output "root: $($a.Hash)"; Write-Output "retrieval: $($b.Hash)"; git log --follow --oneline -- src/retrieval/SPEC.MD
```

**Output:**

```
root: 02AFFA096B34AD7AB00609FD61657F740D4625DBA80FB9B5D06C434F4FFE085F
retrieval: 02AFFA096B34AD7AB00609FD61657F740D4625DBA80FB9B5D06C434F4FFE085F
4bbeada (HEAD -> master) Initial commit: project state through src/evaluation/generate_ground_truth.py (SPEC.MD phases 1-9a)
```

**Diagnosis:** Byte-identical hashes confirmed `src/retrieval/SPEC.MD` was a stray, accidentally-committed duplicate of the root spec (present since the very first commit) — not a functional bug (never imported), but clutter inside a Python package. Removed in Command 30.

---

### Command 30 — Remove the stray duplicate spec file and verify

```powershell
Remove-Item "c:\Users\Tanj\Documents\llmzoomcamp2026\Project\code\src\retrieval\SPEC.MD" -Force; git status --short
```

**Output:**

```
 M docs/PROJECT_NOTES.md
 M src/config.py
 M src/db/monitoring_store.py
 M src/rag/generator.py
 D src/retrieval/SPEC.MD
 M src/retrieval/pipeline.py
?? docs/logs/Phase9b_evaluation-retrieval_CONVERSATION_TRANSCRIPT.md
?? docs/logs/Phase9b_evaluation-retrieval_terminal_logs.md
?? src/evaluation/evaluate_llm.py
?? src/evaluation/evaluate_retrieval.py
```

**Note:** Clean `D src/retrieval/SPEC.MD` deletion, nothing else touched by this command.

---

## Part 4 — Turn 4: This documentation turn

No terminal commands were required to produce this log and its companion conversation transcript (pure file-authoring via `create_file`) — this session's terminal-command history ends at Command 30 above.

---

## Summary of throwaway environments created/destroyed this session

| Venv | Turn | Packages installed | Purpose | Cleaned up? |
|---|---|---|---|---|
| `%TEMP%\venv_evalllm_<guid>` | 1 | `python-dotenv`, `sqlite-vec`, `optimum[onnxruntime]`, `transformers`, `onnxruntime`, `numpy`, `openai`, `google-genai`, `pydantic`, `tenacity` | Full-build smoke test (3 master_table rows, cross-grading, sequential/parallel execution order, both failure paths, `feedback`/`llm_eval_runs` schema, `config.py` no-write-back check) | ✅ (Command 12) |
| `%TEMP%\venv_evalllm2_<guid>` | 2 | Same set | Focused smoke test for the `GENERATION_FAILURE_MODEL` sentinel-detection fix | ✅ (Command 27) |

No throwaway venvs or temp DB/CSV directories were created in Turns 3-4 (static-only review, and pure documentation, respectively).
