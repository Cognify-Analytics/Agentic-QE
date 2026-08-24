---
title: Python Test Location
impact: MEDIUM
impactDescription: keeps generated Python tests in the location the ecosystem and this project expect
tags: python, test-location, tests-directory
---

## Python Test Location

Python tests go in a top-level `tests/` directory, mirroring the `src/` package structure. This is consistent with the Python row of `rules/test-location-map.md`.

### The Convention

```
src/orders.py          → tests/test_orders.py
src/pricing.py         → tests/test_pricing.py
src/api/routes.py       → tests/api/test_routes.py
```

- Mirror the source package's subfolder structure under `tests/`
- Prefix the test file with `test_`, matching the source module name (`orders.py` → `test_orders.py`)
- Shared fixtures go in `conftest.py` at the level of the `tests/` directory (or a subdirectory, if the fixture is scoped to it)
- Large static fixtures (sample files, big JSON/CSV payloads) go in `tests/fixtures/`, not next to the test data builders

### Check the Repo First

Before applying this default, check whether the repo already has an established test location — if tests already exist elsewhere (e.g. `test/` singular, or colocated `*_test.py` next to source), match that instead. **We never invent a test location; the repo's existing convention always wins over this default.** See `rules/test-location-map.md` for the full decision order.

### If Genuinely Nothing Exists Yet

Use `tests/` at the repo root, mirroring `src/`, as shown above. This is the Python default in the shared location table — don't substitute a different convention (e.g. colocated `*_test.py` files) unless the repo already uses one.

### Checklist

- [ ] Checked for an existing test location before defaulting
- [ ] Test file path mirrors the source module's path under `tests/`
- [ ] Test filename is `test_<module_name>.py`
- [ ] Shared fixtures added to the existing `conftest.py`, not duplicated
- [ ] Large fixture files go in `tests/fixtures/`, not inline in the test file
