---
title: Test Case Generation Strategy
impact: HIGH
impactDescription: ensures comprehensive coverage without redundant tests
tags: tests, test-cases, strategy, coverage, branches
---

## Test Case Generation Strategy

Apply strict INCLUDE/EXCLUDE criteria to generate meaningful test cases that cover all code branches without redundancy.

### INCLUDE:
- Each distinct code branch and outcome (success paths, error handling)
- Each unique return value or exception the function can produce
- For HTTP methods: separate cases for status 400, 401, 403 (never merge these)
- Use concrete status codes only
- **Validation constraints**: generate NEGATIVE test cases for each validation rule (invalid input that should fail validation)
- **Custom validators**: generate test cases that trigger validation failure

### EXCLUDE:
- Duplicate scenarios with the same observable result
- Collection size variations (1, 2, 3 elements) unless the code has EXPLICIT size-dependent logic
- Speculative cases (exotic Unicode, massive payload) unless the code explicitly handles them
- Null/None/missing-value arguments, unless the type system, schema, or documentation explicitly allows a missing/null/optional value for that parameter
- Multiple tests for the same exception/error type

**Incorrect:**

```python
# Merging different HTTP status codes
def test_get_user_invalid_request_returns_4xx(): ...

# Testing collection sizes without explicit logic
def test_process_items_one_item_success(): ...
def test_process_items_two_items_success(): ...
def test_process_items_three_items_success(): ...

# Testing None without the type/schema explicitly allowing it
def test_calculate_none_input_raises_exception(): ...
```

**Correct:**

```python
# Separate tests for each HTTP status
def test_get_user_invalid_input_returns_400(): ...
def test_get_user_unauthenticated_returns_401(): ...
def test_get_user_forbidden_returns_403(): ...

# Single test for collection processing (no size-dependent logic)
def test_process_items_valid_list_returns_processed_result(): ...

# Only test None/null if the parameter's type explicitly allows it
def test_calculate_optional_input_none_returns_default(): ...  # only if the signature/schema marks it Optional/nullable
```

### CRITICAL: Private/Internal Functions

When a function calls private/internal helper functions, cover ALL their execution paths indirectly via different inputs to the public function.

### Decision Strategy

Before adding each test case, ask:
1. Does it trigger a DIFFERENT code branch? If no → skip
2. Does it produce a DIFFERENT observable outcome? If no → skip
3. Does the code EXPLICITLY check this condition? If no → skip

**FORBIDDEN:** Using "2xx", "4xx", "5xx" instead of concrete status codes (200, 400, 401, 403, 500).
