# Fix and risk experiment

## Plan recorded before editing

Add one conservative risk signal: deduct 30 points when the original contains
`print(` and the proposed fix contains none. Explain that console output may
have been removed or redirected. Output can be part of a function's observable
behavior; changing it merits review even when the analyzer labels the issue
low severity. The deduction matches the existing missing-return penalty.

Compare the exact same original, Gemini fix, and issue list before and after,
so another model response cannot account for the score difference. Also check
a low-severity logging replacement where the new rule changes auto-fix approval.

This session remained in Default mode; the impact plan was written before the
edit because the assistant could not switch the session to Plan mode.

## Fix selection and constraints

In `bughound_agent.py`, `propose_fix()` returns the original for no issues,
selects the heuristic fixer when no callable client is available, and otherwise
uses the AI fixer. Client exceptions and empty responses trigger heuristic
fallback. A nonempty response is accepted after stripping code fences.

The fixer prompts request full Python code, without Markdown or commentary,
preserving behavior where possible and making the smallest necessary changes.
These are instructions to the model, not enforced guarantees of equivalence.

## Live Gemini fix reviewed

Ran the actual `sample_code/mixed_issues.py` contents with
`gemini-flash-lite-latest` on November 3, 2026. Gemini reported TODO/Low,
print/Low, and bare except/High. The proposed code was:

```python
import logging

# TODO: Replace this with real input validation (this comment is intentional)

def compute_ratio(x, y):
    logging.info("computing ratio...")

    try:
        return x / y
    except (ZeroDivisionError, TypeError):
        return 0
```

The diff adds logging, replaces the print call, and narrows the exception
handler. The TODO, normal division, and fallback return value remain unchanged.
The scope is small, but observable behavior changes: logging can suppress the
former stdout message, and exceptions other than the two named types now
propagate. I would require review, including agreement on intended error
handling and output, before merging.

## Scoring and controlled comparison

The score starts at 100; higher means safer. Existing deductions are 5/20/40
for Low/Medium/High issues, 20 for a rewrite under half the original line count,
30 when all literal `return` text disappears, and 5 when literal `except:`
disappears. Scores are clamped to 0–100. Low risk starts at 75, medium at 40;
only low risk qualifies for auto-fix.

| Identical input/fix/issues | Before | After |
| --- | --- | --- |
| Captured Gemini result above | 45, medium, auto-fix NO | 15, high, auto-fix NO |
| Controlled low-severity `print('Hello')` to `logging.info('Hello')` replacement, preserving `return True` | 95, low, auto-fix YES | 65, medium, auto-fix NO |

The new reason is: “Console output may have been removed or redirected; verify
behavior.” The Gemini result already required review; the controlled boundary
case demonstrates a changed approval decision. The boundary case is synthetic,
not a claimed Gemini output.

This intentionally small text check can flag harmless debug cleanup and miss
partial output removal or alternate spelling such as `print (`. It does not
prove semantic equivalence or execute the proposed fix.

Validation: `.venv/bin/python -m pytest -q` — 23 tests passed, including the
new review requirement and a check that unchanged console output incurs no
new penalty.

## Follow-up: decision regression test

Skimmed all three test modules and ran the baseline: 23 tests passed.
`test_agent_workflow.py` uses `client=None` for heuristic behavior and
`MockClient` for deliberately invalid analyzer output that triggers fallback.
The experiments below used `MockClient` end to end, without API calls.

| Input | Observation before the new guardrail |
| --- | --- |
| Actual `sample_code/cleanish.py` | Zero issues, unchanged code, score 100 / low |
| Actual `sample_code/mixed_issues.py` | Three issues; mock fixer replaces the function with a comment; already blocked at score 0 / high |
| `label = "TODO"` | False positive: TODO inside a string is treated as an unfinished comment. The mock fixer deletes the assignment, yet score 80 / low permits auto-fix |

Plan recorded before editing: address unsafe approval of a comment-only rewrite
in risk assessment. Comparing parsed Python statement lists belongs in the
independent risk layer so the same decision applies to any fixer. If the
original has statements and the proposed fix has none, return score 0 / high
and require human review. Parsing does not execute the supplied code.

Added exactly one workflow test:
`test_comment_only_rewrite_of_executable_code_requires_human_review`.
It uses the existing `MockClient` and asserts no auto-fix, high risk, and a
human-review reflection. With the test added before the guardrail, it failed
at `assert result["risk"]["should_autofix"] is False` because the value was
`True`. After the guardrail, the same test passed. Full suite: 24 tests passed.

Reran the identical three inputs. The weird case changed from 80 / low /
auto-fix YES to 0 / high / auto-fix NO, with the reason “Proposed fix removes
all Python statements. Human review required.” The clean input stayed
unchanged and the mixed input stayed blocked, now with the explicit structural
reason.

This change leaves the TODO false positive and proposed rewrite visible for
review; it blocks their unsafe approval. It does not detect partial statement
loss, prove behavior preservation, or add handling for snippets that fail to
parse. As before, this session remained in Default mode; the plan was written
explicitly before editing rather than claiming a mode switch.
