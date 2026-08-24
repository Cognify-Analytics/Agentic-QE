---
title: Prefer Testing Public APIs Over Private Methods
impact: HIGH
impactDescription: creates resilient tests that survive refactoring
tags: tests, public-api, private-methods, refactoring, resilience
---

## Prefer Testing Public APIs Over Private Methods

Test the public interface of your code. Private/internal functions and implementation-detail classes should be tested indirectly through public APIs.

### Problem: Testing Implementation Details

**Incorrect (Python):**

```python
# Testing a private/internal helper directly
class TestUserInfoValidator:
    def test_validate_future_date_of_birth_raises_exception(self):
        validator = _UserInfoValidator()  # internal, prefixed with "_"

        with pytest.raises(ValidationError):
            validator.validate(info_with_future_dob())

# This test is fragile - if we inline or rename the validator, test breaks
```

**Correct:**

```python
# Test through the public API
class TestUserInfoService:
    def test_save_future_date_of_birth_raises_validation_error(self):
        service = UserInfoService()
        info = create_user_info(date_of_birth=FUTURE_DATE)

        with pytest.raises(ValidationError, match="Invalid date of birth"):
            service.save(info)

    def test_save_valid_info_persists_to_database(self):
        service = UserInfoService()
        info = create_user_info(date_of_birth=PAST_DATE)

        service.save(info)

        assert database.find_by_id(info.id) is not None
```

### When to Test Private/Internal Functions or Classes

Test implementation-detail units separately only when:
1. **Reused across multiple public APIs** — becomes part of the public contract
2. **Complex enough to warrant isolation** — but consider if it should be extracted and made public
3. **Third-party integration** — adapters that wrap external libraries

### Refactoring Freedom

Testing public APIs allows refactoring without changing tests:

```python
# Original implementation
class UserInfoService:
    def __init__(self):
        self._validator = UserInfoValidator()

    def save(self, info):
        self._validator.validate(info)
        write_to_database(info)

# Refactored - validator inlined
class UserInfoService:
    def save(self, info):
        if info.date_of_birth.is_in_future():
            raise ValidationError("Invalid date of birth")
        write_to_database(info)

# Tests don't change because they test the public API!
```

### Guidelines

1. **Test behavior, not implementation** — focus on what, not how
2. **Use public functions/methods as entry points** — even for testing edge cases
3. **Private/internal functions are implementation** — should be covered by public-facing tests
4. **Consider visibility carefully** — if something needs direct testing, maybe it should be public
