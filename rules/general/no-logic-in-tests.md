---
title: Don't Put Logic in Tests
impact: HIGH
impactDescription: prevents bugs in tests and makes expected values obvious
tags: tests, simplicity, kiss, no-logic, readability
---

## Don't Put Logic in Tests

Tests should be straightforward with no conditional logic, loops, or string concatenation. Keep expected values explicit and literal.

### KISS > DRY in Tests

Simplicity is more important than avoiding duplication in tests.

### Problem: Logic Hides Bugs

**Incorrect (Python):**

```python
def test_get_photos_page_url():
    base_url = "http://photos.google.com/"
    url_builder = UrlBuilder(base_url)

    photos_page_url = url_builder.get_photos_page_url()

    # Bug hidden by concatenation: results in "//u/0/photos"
    assert photos_page_url == base_url + "/u/0/photos"
```

**Correct (Python):**

```python
def test_get_photos_page_url_happy_path():
    url_builder = UrlBuilder("http://photos.google.com/")

    actual_url = url_builder.get_photos_page_url()

    # Explicit literal - bug is obvious: "http://photos.google.com//u/0/photos"
    assert actual_url == "http://photos.google.com/u/0/photos"
```

### Avoid These Patterns in Tests

**Incorrect:**

```python
# Loops in tests
for user in users:
    assert user.is_active

# Conditionals in tests
if response.successful:
    assert response.body is not None

# String concatenation in assertions
assert result == "Hello, " + user_name + "!"

# Calculations in assertions
assert total == price * quantity + tax
```

**Correct:**

```python
# Explicit assertions
assert all(user.is_active for user in users)  # only if "all active" IS the behavior under test

# No conditionals - test specific scenarios
assert response.successful is True
assert response.body is not None

# Literal expected values
assert result == "Hello, John!"

# Pre-calculated expected values
expected_total = 115  # 100 * 1 + 15 tax, calculated outside the test
assert total == expected_total
```

### When Logic is Necessary

If tests need complex logic, move it to helper functions with their own tests:

```python
# Helper with its own test coverage
def generate_expected_greeting(user, date):
    # Complex logic here
    ...

# test_generate_expected_greeting verifies this helper works correctly
```

### Key Principles

1. **Use literal values** — not computed values
2. **Avoid operators** — no `+`, `*`, string concatenation in assertions
3. **No control flow** — no `if`, `for`, `while` in test bodies
4. **KISS over DRY** — repetition is OK if it makes tests clearer
