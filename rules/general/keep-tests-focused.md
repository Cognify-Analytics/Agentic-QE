---
title: Keep Tests Focused
impact: HIGH
impactDescription: ensures each test verifies one specific scenario for clear failure messages
tags: tests, focused, single-scenario, single-assertion
---

## Keep Tests Focused

Each test should exercise one specific scenario. Multiple scenarios in one test make failures hard to diagnose.

### Problem: Multiple Scenarios in One Test

**Incorrect:**

```python
def test_withdraw_from_account():
    account.deposit(usd(5))

    # Scenario 1: withdraw within balance
    assert account.withdraw(usd(5)) == OK

    # Scenario 2: withdraw over balance
    assert account.withdraw(usd(1)) == REJECTED

    # Scenario 3: withdraw with overdraft
    account.overdraft_limit = usd(1)
    assert account.withdraw(usd(1)) == OK
# This tests three scenarios, not one!
```

**Correct:**

```python
def test_withdraw_within_balance_succeeds():
    deposit_and_settle(usd(5))

    assert account.withdraw(usd(5)) == OK

def test_withdraw_over_balance_is_rejected():
    deposit_and_settle(usd(5))

    assert account.withdraw(usd(6)) == REJECTED

def test_withdraw_within_overdraft_limit_succeeds():
    deposit_and_settle(usd(5))
    account.overdraft_limit = usd(1)

    assert account.withdraw(usd(6)) == OK
```

### Benefits of Focused Tests

1. **Clear failure messages** — you know exactly what broke
2. **Descriptive names** — each test name describes one scenario
3. **Easy to maintain** — changing one scenario doesn't affect others
4. **Better coverage visibility** — see which scenarios are tested

### When Multiple Assertions Are OK

Multiple assertions are fine when verifying **one behavior** with multiple properties:

```python
def test_create_user_valid_input_returns_complete_user():
    actual_user = user_service.create("john@test.com", "John")

    # All assertions verify the same behavior: user creation
    assert actual_user.id is not None
    assert actual_user.email == "john@test.com"
    assert actual_user.name == "John"
    assert actual_user.created_at is not None
```

### Signs Your Test Is Not Focused

- Test name uses "and" (e.g., `test_deposit_and_withdraw`)
- Multiple "When" or "Act" sections
- State changes between assertions
- Hard to name the test concisely
- Test is longer than 10-15 lines

### Split Unfocused Tests

Ask: "If this test fails, will I know exactly which scenario broke?"

If not, split it into multiple tests.
