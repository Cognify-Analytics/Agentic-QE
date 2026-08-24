---
title: Test Naming Conventions
impact: HIGH
impactDescription: ensures consistent, readable test names that describe behavior
tags: tests, naming, conventions, readability
---

## Test Naming Conventions

Use consistent naming patterns that clearly describe the test scenario and expected outcome.

### Test File/Class Naming

Use the target language's idioms:

| Language | Test file/class naming |
|---|---|
| Java, Kotlin | `[TestedClass]Test` |
| C# | `[TestedClass]Tests` |
| Python | `test_[module_name].py` |
| JavaScript/TypeScript | `[name].test.js` or `[name].spec.ts` |
| Go | `[name]_test.go` |
| Rust | `#[cfg(test)]` module in `[name].rs`, or `tests/[name].rs` |

### Test Method/Function Naming

Format: `{testedMethod}_{givenState}_{expectedOutcome}` (adapt casing to the language's convention — `snake_case` in Python, `camelCase` in Java/JS/Go).

**Incorrect:**

```
# Too vague
def test_calculate(): ...

# No outcome described
def test_calculate_total_valid_products(): ...

# Implementation details instead of behavior
def test_calculate_total_uses_generator_returns_sum(): ...
```

**Correct:**

```python
# Python
def test_calculate_total_valid_products_returns_sum(): ...
def test_calculate_total_empty_list_raises_value_error(): ...
def test_get_user_unauthorized_returns_401(): ...
```

```javascript
// JS/Jest
test('calculateTotal_validProducts_returnsSum', () => { ... });
test('getUser_unauthorized_returns401', () => { ... });
```

```go
// Go
func TestCalculateTotal_ValidProducts_ReturnsSum(t *testing.T) { ... }
func TestGetUser_Unauthorized_Returns401(t *testing.T) { ... }
```

### Naming Guidelines

1. **Be specific about the state/condition** — "validProducts" not "goodInput"
2. **Be specific about the outcome** — "returns401" not "fails"
3. **Use domain language** — "unauthorized" not "noToken"
4. **Avoid technical jargon** — describe behavior, not implementation
