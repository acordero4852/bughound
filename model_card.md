# BugHound Mini Model Card (Reflection)

Completed November 3, 2026. Based on local offline experiments and live Gemini
runs using `gemini-flash-lite-latest`. This describes the current implementation,
including the three reliability changes made during the activity.

## 1) What is this system?

**Name:** BugHound.

**Purpose:** Analyze short Python snippets, propose fixes, display a diff, and
recommend whether a proposed change qualifies for automatic application under
a simple risk policy. The app displays the recommendation and proposed code;
it does not write the fix into the original sample file.

**Intended users:** Students learning agentic workflows and developers exploring
AI-assisted debugging. Its limited checks do not establish correctness or
replace code review. Gemini is an external model; no model was trained here.

**Changes built:** Strict validation of analyzer issue fields with heuristic
fallback; a penalty for removing or redirecting console output; and a hard
review requirement when a rewrite removes all Python statements.

## 2) How does it work?

The loop is implemented in `BugHoundAgent.run()`:

1. **PLAN:** Log the intent to scan the snippet and propose a fix. This is a
   fixed workflow, rather than a model-generated plan.
2. **ANALYZE:** With `client=None`, check text patterns for `print(`, bare
   `except:`, and `TODO`. With a client exposing `complete()`, request AI
   analysis. The expected response is a JSON array of objects with nonempty
   string fields `type`, `severity`, and `msg`; severity must be `Low`,
   `Medium`, or `High`. Valid `[]` means no issues. Client exceptions or invalid
   output trigger heuristics. The updated validator rejects the whole array if
   any entry violates that contract. Existing extraction of arrays from
   surrounding text remains permissive.
3. **ACT:** If there are no issues, return the original code. Without a client,
   apply heuristic replacements for prints and bare exception handlers.
   Otherwise request a full rewrite from the client. The fixer prompts ask for
   minimal changes, preserved behavior where possible, and Python code without
   Markdown. Exceptions or empty output trigger the heuristic fixer. Nonempty
   output is accepted after stripping code fences; behavior preservation is
   not enforced at this step.
4. **TEST:** Call the local risk assessor. It checks severity, text changes,
   and whether parsed Python statements disappeared. This stage does not run
   the submitted program or its tests.
5. **REFLECT:** Read `should_autofix` and announce either eligibility under the
   policy or a recommendation for human review. There is no retry loop.

The current UI's **Heuristic only (no API)** setting supplies `MockClient`,
which exposes `complete()`. Consequently, its trace says “Using LLM analyzer,”
then falls back because the mock returns invalid JSON. For fixes, the mock
returns a comment-only placeholder, which is nonempty and does not trigger
fallback. This differs from direct `client=None` heuristic behavior. Neither
offline path calls an API. Gemini mode sends analysis and, when issues exist,
fix requests to Gemini. The wrapper converts API failures into empty output,
so a fallback log does not necessarily identify the underlying API error.

## 3) Inputs and outputs

Inputs were the actual sample files, rather than the app's shorter built-in
sample strings. They contain small functions, logging or print calls, division,
and file-reading try/except blocks. A one-line string assignment provided an
additional edge case.

Outputs include issue objects, full proposed code, a unified diff, a risk score,
risk level, reasons, auto-fix recommendation, and the ordered Agent Trace.

| Tested input and mode | Issues and proposed change | Observed risk report |
| --- | --- | --- |
| `sample_code/cleanish.py`, offline MockClient | No issues; logging-based addition function left unchanged | 100 / low / auto-fix YES, with no actual edit |
| `sample_code/mixed_issues.py`, offline MockClient | Print/Low, bare except/High, TODO/Medium; proposed rewrite was only the mock placeholder comment | 0 / high / NO, both before and after the statement-loss guardrail; the new report explicitly identifies statement removal |
| `sample_code/mixed_issues.py`, live Gemini | TODO/Low, print/Low, bare except/High; one captured fix added logging and narrowed the handler to `(ZeroDivisionError, TypeError)`, retaining both returns and the TODO | 45 / medium / NO initially; rescoring the identical captured fix with the output-removal penalty produced 15 / high / NO |
| `sample_code/flaky_try_except.py`, live Gemini | Bare except/High plus potential file-handle leak/Medium; proposed `with open(...)` and `except Exception` | 35 / high / NO; the live rerun after analyzer validation retained the same categories and severities |
| `label = "TODO"`, offline MockClient | False TODO-comment issue/Medium; placeholder rewrite deleted the assignment | Before statement-loss guardrail: 80 / low / YES. After: 0 / high / NO |

Direct heuristic analysis of `flaky_try_except.py` found only the bare except.
Direct heuristic analysis of `mixed_issues.py` found the same three patterns as
the offline UI fallback.

For a controlled format-failure experiment, a replay client returned `[null]`
for `mixed_issues.py`. Before strict validation this became an empty issue
list; afterward it triggered fallback and returned three heuristic issues.
This response was injected, not observed from Gemini. Likewise, the controlled
logging-only change from 95 / low / YES to 65 / medium / NO was a synthetic
boundary case, not a claimed Gemini result.

## 4) Reliability and safety rules

The score starts at 100 and is clamped to 0–100; higher means safer under these
rules, not a measured probability of correctness. Low risk starts at 75,
medium at 40, and only low risk qualifies for auto-fix. Empty fixes and complete
statement loss have hard-stop reports of 0 / high / NO.

| Current rule | Why it matters | Possible false positive | Possible false negative |
| --- | --- | --- | --- |
| Deduct 5/20/40 for each Low/Medium/High issue | Escalates changes involving serious findings | A false or exaggerated analyzer finding lowers the score even when the proposed change is safe. The TODO string was an actual false finding. | Missed or understated issues add little or no penalty; severity does not measure whether the fix introduces a new bug. |
| Deduct 30 if the original contains `print(` and the fix contains none | Console output can be observable behavior; logging may suppress a formerly visible message | Intentional removal of debug prints, or matching text inside a comment/string, can cause an unnecessary review penalty. | Removing only some prints, changing printed values, or spelling calls as `print (` can evade the check. |
| Return 0 / high / NO if the original AST has statements and the fixed AST has none | Blocks a comment-only rewrite from deleting the entire program despite a favorable severity score | An intentionally retired module whose approved replacement is comments would still require review. | Removing only some statements, retaining a harmless statement/docstring, or producing invalid syntax can evade this particular comparison. Syntax errors currently skip it. |

Other rules deduct 20 for a rewrite shorter than half the original line count,
30 when all literal `return` text disappears, and 5 when literal `except:`
disappears. These text and size checks are warnings, not semantic comparisons.
For example, a changed return value can retain the word `return` and avoid
that penalty entirely.

## 5) Observed failure modes

1. **False positive followed by unsafe confidence:** `label = "TODO"` contains
   a string, not an unfinished comment. The heuristic still flagged it.
   MockClient then proposed only `# MockClient: no rewrite available in offline mode.`
   Both versions had one line, no print, and no return, so the old checks
   approved deletion at score 80. The new AST guardrail blocks approval, while
   leaving the false finding and proposed rewrite visible for review.
2. **A real issue missed by heuristics:** In `flaky_try_except.py`, `f.close()`
   follows `f.read()` rather than being guaranteed by a context manager. Gemini
   identified a possible leak if reading raises; the heuristic only found the
   bare except. Pattern checks did not understand the resource lifetime.
3. **Over-editing and misleading operational state:** With the offline UI's
   MockClient, the entire `compute_ratio()` function in `mixed_issues.py` was
   replaced by the placeholder comment. The trace called this an LLM fix even
   though no model or API was involved. Existing scoring blocked that example,
   but the TODO-string example showed the same failure could be approved.
4. **Risky behavior changes despite minimal-looking diffs:** Gemini's captured
   `mixed_issues.py` fix kept `return x / y` and `return 0`, but narrowed the
   exception handler and replaced stdout output with logging. Exceptions
   outside the selected types now propagate; the console message may disappear.
   I would not merge this without confirming intended error and output behavior.

The mock's invalid analyzer JSON also exercised a real format-fallback path.
The live Gemini responses inspected here were accepted; they did not exhibit
the deliberately injected `[null]` failure.

## 6) Heuristic vs Gemini comparison

Heuristics consistently caught the literal print, bare except, and TODO patterns
in `mixed_issues.py`. Their categories and severities were predictable, but
they lacked context: a TODO inside a string was still reported, and the
file-handle leak was missed.

Gemini identified the leak and proposed a context manager. It assigned the
mixed sample's TODO Low severity instead of the heuristic's Medium, and used
more specific explanations. Repeated live runs varied in wording and fix
details. One earlier mixed-sample fix removed the TODO and print; the later
captured fix retained the TODO and substituted logging.

The direct heuristic fixer uses text replacements: add logging, replace prints,
and replace bare except with `except Exception as e:`. Gemini could choose a
context manager or specific exception types. The offline UI's mock placeholder
is a wiring problem, not evidence that the direct heuristic fixer always
deletes code.

The scorer's review recommendations for the Gemini samples matched my caution.
The original approval of the TODO-string deletion did not. The new guardrails
improve those observed decisions, but a low-risk category alone still cannot
establish behavior preservation.

## 7) Human-in-the-loop decision

**Scenario:** A rewrite replaces a functioning assignment or function with only
comments, as observed with `label = "TODO"` and MockClient.

**Trigger and location:** Implemented in `reliability/risk_assessor.py`: parse
both snippets without executing them; when the original AST body is nonempty
and the fixed AST body is empty, require review regardless of severity. The
independent risk layer applies the same policy to any fix source. The agent
reads the decision and the UI displays its reason.

**Message:** “Proposed fix removes all Python statements. Human review required.”

**Evidence:** Added
`test_comment_only_rewrite_of_executable_code_requires_human_review` using the
existing MockClient. It asserts no auto-fix, high risk, and a human-review
reflection. It failed before the guardrail because auto-fix was `True`, and
passed afterward. The full offline suite finished with **24 passing tests**.

## 8) Improvement idea

**Reject syntactically invalid proposed fixes before scoring them as safe.**
The risk assessor already calls `ast.parse()`, but catches `SyntaxError` and
continues with text-based scoring. Make failure to parse the *fixed* code a
hard stop: score 0, high risk, no auto-fix, with the reason “Proposed fix is not
valid Python; human review required.” Parse the fixed code independently so an
invalid original does not prevent this validation.

Measure success with an offline mocked fixer response such as `def broken(:`:
the decision must be high risk/no auto-fix, while existing valid-input cases
continue to pass. This is a proposed next change, not part of the implemented
24-test result. It adds a small check without executing untrusted snippets or
claiming that syntax validity proves correctness.

Experiment details: [analysis notes](ANALYSIS_NOTES.md) and
[fix/risk notes](RISK_NOTES.md). These are small educational examples, not a
benchmark or an estimate of production reliability.
