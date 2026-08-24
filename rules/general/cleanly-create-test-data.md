---
title: Cleanly Create Test Data
impact: HIGH
impactDescription: improves test readability and maintainability through clean data setup
tags: tests, test-data, helpers, builders, readability
---

## Cleanly Create Test Data

Use helper functions and builder patterns to create test data cleanly. Avoid cluttering tests with irrelevant details.

### Use Helper Functions

Helper functions hide irrelevant details and make tests easier to read.

**Incorrect (Python):**

```python
def test_calculate_total_multiple_items_happy_path():
    cart = ShoppingCart(DefaultRoundingStrategy(), "unused", "NORMAL", False, False, "UTC", None)
    total = cart.calculate_total(new_item_1(), new_item_2(), new_item_3())
    assert total == 25  # Where did this number come from?
```

**Correct (Python):**

```python
def test_calculate_total_multiple_items_happy_path():
    cart = new_shopping_cart()

    actual_total = cart.calculate_total(
        new_item_with_price(10),
        new_item_with_price(10),
        new_item_with_price(5),
    )

    expected_total = 25
    assert actual_total == expected_total
```

**Correct (JS/Jest):**

```javascript
test('calculateTotal_multipleItems_happyPath', () => {
  const cart = newShoppingCart();

  const actualTotal = cart.calculateTotal(
    newItemWithPrice(10),
    newItemWithPrice(10),
    newItemWithPrice(5),
  );

  const expectedTotal = 25;
  expect(actualTotal).toBe(expectedTotal);
});
```

### Use the Test Data Builder Pattern

When helper functions grow with many parameters, use the builder pattern (or, in languages without one, keyword arguments with sensible defaults).

**Incorrect:**

```python
# Helper functions become unwieldy with many positional parameters
small = new_company(2, 2, None, "PUBLIC")
privately_owned = new_company(None, None, None, "PRIVATE")
bankrupt = new_company(None, None, PAST_DATE, "PUBLIC")
```

**Correct (Python — keyword defaults as a builder substitute):**

```python
def new_company(*, employees_count=None, board_members_count=None,
                 bankruptcy_date=None, type="PUBLIC"):
    return Company(employees_count, board_members_count, bankruptcy_date, type)

small = new_company(employees_count=2, board_members_count=2)
privately_owned = new_company(type="PRIVATE")
bankrupt = new_company(bankruptcy_date=PAST_DATE)
arbitrary_company = new_company()
```

**Correct (Go — functional options as the builder equivalent):**

```go
func NewCompany(opts ...CompanyOption) *Company {
    c := &Company{Type: Public}
    for _, opt := range opts {
        opt(c)
    }
    return c
}

small := NewCompany(WithEmployeesCount(2), WithBoardMembersCount(2))
bankrupt := NewCompany(WithBankruptcyDate(pastDate))
```

### Never Rely on Default Values from Helpers

If a test depends on a value, explicitly set it even if it matches the helper's default.

**Incorrect:**

```python
def new_company(type="PUBLIC"):
    return Company(type=type)

def test_public_company():
    # Relies on helper's default - fragile!
    company = new_company()
    # ...
```

**Correct:**

```python
def test_public_company():
    # Explicitly set the value this test depends on
    company = new_company(type="PUBLIC", board_members_count=0)
    # ...
```

### Helper Function Guidelines

1. **Name helpers descriptively** — `create_product_with_category("Office")` not `create_product()`
2. **Only expose relevant parameters** — hide irrelevant details
3. **Keep helpers simple** — no business logic
4. **Consider builders/factory functions for complex objects** — when many field combinations are needed
