---
title: Pytest Conventions
impact: HIGH
impactDescription: keeps generated Python tests idiomatic and consistent with the pytest ecosystem
tags: python, pytest, conventions, fixtures, parametrize
---

## Pytest Conventions

Use pytest idioms, not a ported-over xUnit/JUnit style. No assertion library is needed — plain `assert` is the convention.

### File and Function Structure

- One test file per source module: `src/orders.py` → `tests/test_orders.py`
- Test functions are free functions named `test_<method>_<state>_<outcome>`, not methods on a class, unless the project's existing tests already group with a `Test*` class
- If the project does use classes, name them `Test<Subject>` (no `__init__`, pytest collects by name only)

```python
# tests/test_orders.py
def test_create_order_valid_request_returns_order_id():
    ...

def test_create_order_empty_items_raises_validation_error():
    ...
```

### Fixtures via `conftest.py`

Put shared fixtures in `conftest.py` in the same directory as the tests (or a parent directory for repo-wide fixtures). Never redefine a fixture that already exists — extend or parametrize it instead.

```python
# tests/conftest.py
import pytest

@pytest.fixture
def order_factory():
    def _make(**overrides):
        defaults = {"customer_id": "cust-1", "items": []}
        defaults.update(overrides)
        return Order(**defaults)
    return _make
```

```python
# tests/test_orders.py
def test_create_order_valid_request_returns_order_id(order_factory):
    order = order_factory(items=[{"sku": "A", "qty": 1}])
    ...
```

Use fixtures for infrastructure and reusable object factories — not to hide test-specific data the test's outcome depends on (see `rules/general/keep-cause-effect-clear.md`).

### Table-Driven Cases with `@pytest.mark.parametrize`

When several cases only differ by input/expected-output values, parametrize instead of copy-pasting near-identical test functions.

```python
import pytest

@pytest.mark.parametrize(
    "quantity, unit_price, expected_total",
    [
        (1, 10.0, 10.0),
        (2, 10.0, 20.0),
        (0, 10.0, 0.0),
    ],
)
def test_calculate_total_various_quantities_returns_expected(quantity, unit_price, expected_total):
    actual_total = calculate_total(quantity, unit_price)
    assert actual_total == expected_total
```

Give each parametrized case a clear id if the values alone aren't self-explanatory:

```python
@pytest.mark.parametrize(
    "status_code, expected_label",
    [(400, "bad_request"), (401, "unauthorized"), (403, "forbidden")],
    ids=["400", "401", "403"],
)
def test_status_label_maps_correctly(status_code, expected_label):
    ...
```

### Exception Testing with `pytest.raises`

Use `pytest.raises` as a context manager; assert on the message with `match` when the message matters to the behavior under test.

```python
import pytest

def test_create_order_empty_items_raises_validation_error():
    with pytest.raises(ValidationError, match="items must not be empty"):
        create_order(customer_id="cust-1", items=[])
```

### Assertions

Plain `assert` with a plain expression is the pytest convention — no `assertEqual`, no third-party assertion library needed. Pytest's assertion rewriting gives readable failure output automatically.

```python
actual_total = calculate_total(items)
expected_total = 25
assert actual_total == expected_total
```

### Checklist

- [ ] Test file mirrors the source module under `tests/`
- [ ] Fixtures live in `conftest.py`, reused rather than duplicated
- [ ] Table-driven cases use `@pytest.mark.parametrize`, not copy-pasted functions
- [ ] Exception cases use `pytest.raises`
- [ ] Assertions are plain `assert` expressions
