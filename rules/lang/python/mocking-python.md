---
title: Mocking in Python
impact: HIGH
impactDescription: keeps mocking minimal, targeted, and idiomatic to unittest.mock/pytest-mock
tags: python, mocking, unittest.mock, pytest-mock
---

## Mocking in Python

Use `unittest.mock` (`Mock`, `MagicMock`, `patch`) or `pytest-mock`'s `mocker` fixture. Mock only true externalities — never simple value objects, and never the system under test itself. This mirrors the general principle in `rules/general/general-principles.md` rule #5: minimal, targeted mocking.

### What to Mock

Mock things the test cannot control or that are slow/unsafe to exercise for real:
- Network calls (HTTP clients, third-party API SDKs)
- Filesystem access
- The system clock / `time.time()` / `datetime.now()`
- Randomness (`random`, `uuid.uuid4`)
- Databases and other external services

### What NOT to Mock

Use real objects for:
- Value objects, dataclasses, DTOs (`Order`, `Product`, `User`) — construct them for real
- Pure functions and simple collaborators with no side effects
- The function/class under test

**Incorrect:**

```python
def test_process_order(mocker):
    mock_product = mocker.Mock()
    mock_product.price = 100.0
    mock_product.name = "Test"
    # Over-mocking a plain value object
    ...
```

**Correct:**

```python
def test_process_order_valid_product_calculates_total():
    product = Product(name="Test", price=100.0)  # real object

    actual_result = service.process_order(product)

    assert actual_result.total == 100.0
```

### Using `unittest.mock`

```python
from unittest.mock import Mock, patch

def test_get_user_calls_repository_once():
    repository = Mock()
    repository.find_by_id.return_value = User(id="1", name="John")
    service = UserService(repository)

    actual_user = service.get_user("1")

    assert actual_user.name == "John"
    repository.find_by_id.assert_called_once_with("1")
```

```python
@patch("src.orders.requests.post")
def test_submit_order_calls_payments_api(mock_post):
    mock_post.return_value.status_code = 200

    submit_order(order)

    mock_post.assert_called_once()
```

### Using `pytest-mock`'s `mocker` Fixture

Prefer `mocker` over `@patch` decorators in pytest-based projects — it composes better with fixtures and auto-undoes patches after the test.

```python
def test_submit_order_calls_payments_api(mocker):
    mock_post = mocker.patch("src.orders.requests.post")
    mock_post.return_value.status_code = 200

    submit_order(order)

    mock_post.assert_called_once()
```

### Faking the Clock and Randomness

Inject a fixed value rather than patching global state where the code allows it; patch only when there's no injection seam.

```python
def test_create_order_sets_timestamp(mocker):
    mocker.patch("src.orders.datetime.now", return_value=datetime(2024, 1, 1))

    actual_order = create_order()

    assert actual_order.timestamp == datetime(2024, 1, 1)
```

### Verify Only Relevant Arguments

Don't assert on every argument of a mocked call — see `rules/general/verify-relevant-arguments-only.md`. Use `mock.ANY` for arguments this test doesn't care about.

```python
from unittest.mock import ANY

service.notify(user, message, timestamp)

notifier.send.assert_called_once_with(user.email, message, ANY)
```

### Checklist

- [ ] Only true externalities (network, filesystem, clock, randomness, external services) are mocked
- [ ] Value objects and DTOs are constructed as real objects, not mocked
- [ ] `mocker` fixture used in preference to `@patch` decorators where the project uses pytest
- [ ] Irrelevant arguments use `mock.ANY`, not exact-value assertions
