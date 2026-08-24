---
title: Existing Test Awareness
impact: HIGH
impactDescription: prevents duplicate tests and ensures consistency with project conventions
tags: tests, awareness, duplicates, conventions, style
---

## Existing Test Awareness

Before generating tests, check what already exists. Match the project's testing conventions and avoid duplicating coverage.

### Before Generating: Check for Existing Tests

1. **Look for an existing test file** for the target:
   - Search for the file/module's conventional test counterpart (e.g. `test_orders.py` for `orders.py`, `orders.test.ts` for `orders.ts`, `OrderServiceTest.java` for `OrderService.java`)
   - If found, read it fully before generating anything

2. **If an existing test file is found:**
   - Do NOT create a second test file — add missing test cases to the existing one
   - Preserve existing test structure, imports, and helper functions
   - Follow the same patterns (naming, assertion style, setup approach) already used
   - Only add tests for behaviors not yet covered

3. **If no existing test file is found:**
   - Scan 2–3 neighboring test files to learn project conventions
   - Match the style: import order, assertion/matcher style, naming pattern, comment style

### What to Match from Existing Tests

- **Assertion/matcher style**: If the project uses plain `assert` expressions, don't switch to an assertion library (and vice versa); if it uses one matcher library, don't introduce a second
- **Test data patterns**: If the project has factory functions, fixtures, or builders, use them
- **Shared setup/base classes**: If tests share a `conftest.py` fixture, a base test class, or a common setup helper, follow that pattern
- **Import style**: Match how the project imports assertion/test utilities
- **Comment style**: If existing tests use `# given / when / then` vs `# arrange / act / assert`, match it

### What NOT to Do

**Incorrect:**

```python
# Creating a new test file when one already exists
# File: tests/test_user_service_new.py (NEW - duplicate!)
class TestUserService:
    # 10 test methods, 5 of which already exist in test_user_service.py
    ...
```

**Correct:**

```python
# Adding only missing tests to the existing file
# File: tests/test_user_service.py (EXISTING - appended to)

# ... existing tests preserved as-is ...

# New tests added below existing ones
def test_update_user_invalid_email_raises_validation_error():
    ...
```

### Decision Checklist

Before writing any test code, verify:
- [ ] Searched for an existing test file for the target
- [ ] Read existing tests to understand what's already covered
- [ ] Identified project test conventions from neighboring test files
- [ ] Confirmed which behaviors still need test coverage
