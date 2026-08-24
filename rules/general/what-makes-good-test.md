---
title: What Makes a Good Test
impact: HIGH
impactDescription: defines core qualities that every test should have
tags: tests, quality, clarity, completeness, conciseness, resilience
---

## What Makes a Good Test

Every good test should have four qualities: Clarity, Completeness, Conciseness, and Resilience.

### 1. Clarity

A test should be easy to read and understand at a glance.

**Signs of clarity:**
- Test name describes the scenario
- Given-When-Then structure is obvious
- No need to look elsewhere to understand the test

**Incorrect (Python):**

```python
def test1():
    x = svc.process(get_data())
    assert x.is_valid
```

**Correct:**

```python
def test_process_valid_input_returns_valid_result():
    # Given
    input = create_valid_input()

    # When
    actual_result = service.process(input)

    # Then
    assert actual_result.is_valid
```

### 2. Completeness

A test should contain all information needed to understand it without looking elsewhere.

**Incorrect:**

```python
# Relies on module-level constants and a shared fixture
def test_calculation():
    assert calculator.calculate() == EXPECTED_VALUE
```

**Correct:**

```python
def test_calculate_multiple_items_returns_sum_of_prices():
    # All relevant data is visible in the test
    calculator.add(new_item_with_price(10))
    calculator.add(new_item_with_price(20))

    actual_total = calculator.calculate()

    expected_total = 30
    assert actual_total == expected_total
```

### 3. Conciseness

A test should contain only information relevant to the scenario. Hide irrelevant details.

**Incorrect:**

```python
def test_get_user_existing_user_returns_user():
    user = User()
    user.id = "123"
    user.name = "John"
    user.email = "john@test.com"
    user.created_at = now()
    user.updated_at = now()
    user.role = Role.USER
    user.active = True
    # ... more irrelevant setup
```

**Correct:**

```python
def test_get_user_existing_user_returns_user():
    # Helper hides irrelevant details
    user = create_user("123", "John")
    repository.find_by_id.return_value = user

    actual_user = service.get_user("123")

    assert actual_user.name == "John"
```

### 4. Resilience

A test should not break when unrelated code changes. It should only fail when the tested behavior breaks.

**Signs of resilience:**
- Tests behavior, not implementation
- Uses public APIs
- Doesn't over-specify mock interactions
- Doesn't rely on specific field order or formatting

**Incorrect:**

```python
# Brittle: breaks if JSON key order changes
assert response.body == '{"name":"John","age":30}'
```

**Correct:**

```python
# Resilient: only checks relevant fields
body = response.json()
assert body["name"] == "John"
```

### Summary Checklist

- [ ] **Clarity**: Can I understand this test in 10 seconds?
- [ ] **Completeness**: Is all relevant information in the test?
- [ ] **Conciseness**: Is irrelevant information hidden?
- [ ] **Resilience**: Will this test survive refactoring?
