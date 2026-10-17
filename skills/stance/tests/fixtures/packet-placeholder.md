# Context packet — t1 / Step 1

**Goal:** Add `mul(a, b)` to calc.py with a unit test.

**Task type:** mechanical

**Working directory:** {{WORKDIR}}

**You own (only these files):**
- `calc.py`
- `test_calc.py`
- `missing.py`
- `docs/USAGE.md` (new)

**Do not touch:** everything else.

**Contracts and interfaces you must respect:**
- `add(a, b)` and `sub(a, b)` keep their signatures.

**Rules that bind here:** <project hard rules from its AGENTS.md>

**Already done / context you would otherwise re-read:**
- calc.py has add and sub; tests use unittest.

**Smoke test:** none

**Fallback:** none

**Acceptance (all must pass; the dispatcher re-runs these):**
- `python3 -m unittest` passes
- `grep -q "def mul" calc.py`

**Report format:** end with exactly:
```text
STATUS: done | blocked
FILES: <files changed, or none>
BLOCKERS: <verbatim error and what you tried, or none>
NOTES: <one line>
```
