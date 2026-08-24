---
title: Test Behaviors, Not Methods
impact: HIGH
impactDescription: creates resilient tests that survive refactoring
tags: tests, behaviors, resilient, maintainable
---

## Test Behaviors, Not Methods

Structure tests around behaviors (what the system does), not around methods (how it's implemented).

### Problem: Testing a Method

**Incorrect (Python):**

```python
def test_reset_password():
    user = User(password="lost password")

    user_service.reset_password(user)

    # Testing multiple behaviors in one test
    assert user.password == ""
    assert user.mailbox.messages[0].title == "Password reset"
    assert user.mailbox.messages[0].body.startswith("You have requested password reset")
    assert counter.get("reset password") == 1
```

**Correct:**

```python
def test_reset_password_clears_existing_password():
    user = User(password="1234")

    user_service.reset_password(user)

    assert user.password == ""

def test_reset_password_sends_notification_email():
    user = User(password="1234")

    user_service.reset_password(user)

    assert user.mailbox.messages[0].title == "Password reset"
    assert user.mailbox.messages[0].body.startswith("You have requested password reset")

def test_reset_password_increments_reset_counter():
    user = User(password="1234")

    user_service.reset_password(user)

    assert counter.get("reset password") == 1
```

### Benefits

1. **Clear test names** — each test describes one behavior
2. **Focused failures** — when a test fails, you know which behavior broke
3. **Easier refactoring** — changes to one behavior don't affect other tests
4. **Better documentation** — tests describe what the system does

### Identifying Behaviors

Ask: "What are the observable effects of this action?"

For `reset_password()`:
- User's password becomes empty
- User receives an email
- Reset counter is incremented

Each of these is a separate behavior that should have its own test.

### One Behavior Can Have Multiple Assertions

Testing the email notification behavior:

```python
def test_reset_password_sends_correct_notification_email():
    user = User(password="1234", email="john@test.com")

    user_service.reset_password(user)

    # Multiple assertions about the same behavior (the email)
    actual_email = user.mailbox.messages[0]
    assert actual_email.to == "john@test.com"
    assert actual_email.title == "Password reset"
    assert actual_email.body.startswith("You have requested")
```

### Naming Pattern

Name tests after the behavior, not the method:
- `reset_password_clears_password` — describes behavior
- `test_reset_password` — describes method (bad)
