---
title: Only Verify Relevant Method Arguments
impact: MEDIUM
impactDescription: reduces test fragility and focuses verification on tested behavior
tags: tests, verification, mocks, arguments, focused
---

## Only Verify Relevant Method Arguments

When verifying mock/stub interactions, only check arguments that are relevant to the specific behavior being tested. Use a wildcard/any-value matcher for irrelevant arguments.

### Problem: Over-Specified Verification

**Incorrect (Python, unittest.mock):**

```python
def test_display_greeting_shows_special_greeting_on_new_years_day():
    clock.set_time(NEW_YEARS_DAY)
    user.name = "Frank Sinatra"

    user_greeter.display_greeting()

    # Verifying ALL arguments - fragile!
    user_prompter.update_prompt.assert_called_once_with(
        "Hi Frank Sinatra! Happy New Year!",
        TitleBar.of("2024-01-01"),
        PromptStyle.NORMAL,
    )
# This test breaks if TitleBar format or PromptStyle changes,
# even though it's testing the greeting message
```

**Correct:**

```python
def test_display_greeting_shows_special_greeting_on_new_years_day():
    clock.set_time(NEW_YEARS_DAY)
    user.name = "Frank Sinatra"

    user_greeter.display_greeting()

    # Only verify the argument this test cares about
    actual_message = user_prompter.update_prompt.call_args.args[0]
    assert actual_message == "Hi Frank Sinatra! Happy New Year!"

def test_display_greeting_uses_title_bar_with_current_date():
    clock.set_time(NEW_YEARS_DAY)

    user_greeter.display_greeting()

    # This test focuses on the title bar argument only
    actual_title_bar = user_prompter.update_prompt.call_args.args[1]
    assert actual_title_bar == TitleBar.of("2024-01-01")

def test_display_greeting_uses_normal_prompt_style():
    user_greeter.display_greeting()

    # This test focuses on the prompt style argument only
    actual_style = user_prompter.update_prompt.call_args.args[2]
    assert actual_style == PromptStyle.NORMAL
```

### Benefits

1. **Focused tests** — each test verifies one behavior
2. **Resilient tests** — changes to unrelated arguments don't break tests
3. **Clear intent** — obvious what behavior is being tested

### When to Verify All Arguments

Verify all arguments only when they're all relevant to the behavior:

```python
def test_send_email_all_fields_are_correct():
    # When testing the complete email composition
    order_service.send_confirmation(order)

    email_service.send.assert_called_once_with(
        "customer@test.com",
        "Order Confirmation #123",
        mock.ANY,  # body checked separately, or with a "contains" style check
    )
```

### Capturing and Inspecting the Real Argument

For complex objects, capture the real argument passed to the mock and verify only the relevant field(s), instead of asserting on the whole object. Every mocking framework has an equivalent mechanism — `unittest.mock`'s `call_args`/`call_args_list`, `pytest-mock`'s `mocker.spy`, Jest/Sinon's `mock.calls`, Java Mockito's `ArgumentCaptor`, Go table-driven fakes, or RSpec's argument matchers.

```python
def test_create_order_sets_correct_product_id():
    order_service.create_order(OrderRequest("product-123", 5))

    saved_order = repository.save.call_args.args[0]
    # Only verify the field relevant to this test
    assert saved_order.product_id == "product-123"
```
