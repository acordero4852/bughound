# Analysis reliability experiment

## Plan recorded before editing

Validate every model issue against the analyzer prompt's contract. Reject the
whole response on an invalid entry and use the existing heuristic fallback.
Keep valid empty arrays acceptable. This prevents malformed entries from
silently turning into a clean report, at the cost of discarding valid AI
findings when another entry in the same response is malformed.

## Expected output and routing

The analyzer prompts request a JSON array of objects with nonempty string
fields `type`, `severity`, and `msg`. Severity must be `Low`, `Medium`, or
`High`; `[]` means no issues.

`analyze()` uses heuristics when no client with `complete()` is available.
Otherwise it calls the client, parses JSON in `_parse_json_array_of_issues()`,
and validates entries in `_normalize_issues()`. Call exceptions or rejected
output trigger heuristics. Existing extraction of JSON arrays from surrounding
text remains unchanged; this experiment tightens issue validation.

The app's heuristic setting supplies a `MockClient`, which enters the AI route
and then falls back during analysis. It makes no API calls.

## Live Gemini observations

Model: `gemini-flash-lite-latest`, on November 3, 2026. Inputs were the actual
file contents, rather than the app's built-in sample strings.

| Input | Heuristic analysis | Gemini analysis before the change |
| --- | --- | --- |
| `mixed_issues.py` | Print: Low; bare except: High; TODO: Medium | Print/readability: Low; bare except/correctness: High; TODO/maintainability: Low |
| `flaky_try_except.py` | Bare except: High | Bare except: High; possible file-handle leak during `read()`: Medium |

Both live responses were accepted without fallback. After the change, rerunning
the identical `flaky_try_except.py` input accepted the same two issue categories
and severities, with slightly different wording. Its risk score remained 35,
high risk, with auto-fix declined.

## Controlled before/after

To isolate validation from model variability, replayed the identical analyzer
response `[null]` against the same `sample_code/mixed_issues.py` contents:

| Version | Analysis result | Fallback |
| --- | --- | --- |
| Before | Zero issues; invalid entry silently discarded | No |
| After | Three heuristic issues: print, bare except, TODO | Yes, explicitly logged |

`[null]` was injected by a replay client; it was not observed from Gemini.
Valid JSON `[]` remains accepted without fallback. Missing/blank/non-string
fields, non-object entries, unsupported severities, and mixed valid/invalid
arrays now cause the entire analysis response to fall back.

Validation: `.venv/bin/python -m pytest -q` — 21 tests passed.
The focused regression cases are in `tests/test_analyzer_validation.py`.
