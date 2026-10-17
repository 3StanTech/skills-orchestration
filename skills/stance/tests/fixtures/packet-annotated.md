# Context packet — t1 / Step 1

**Goal:** Add `mul(a, b)` to calc.py with a unit test.

**Task type:** mechanical

**Working directory:** {{WORKDIR}}

**You own (only these files):**
- `calc.py` (edit only `mul` and its docstring; `add` and `sub` stay as they are)
- `test_calc.py` — append the `mul` cases at the end
- `docs/USAGE.md` (new) (one example per function)

**Do not touch:** everything else.

**Contracts and interfaces you must respect:**
- `add(a, b)` and `sub(a, b)` keep their signatures.

**Rules that bind here:** stdlib only.

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
