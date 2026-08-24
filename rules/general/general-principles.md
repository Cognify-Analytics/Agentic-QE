---
title: General Test Principles
impact: HIGH
impactDescription: ensures tests are maintainable, reliable, and focused on behavior
tags: tests, principles, patterns, best-practices
---

## General Test Principles

Follow these core principles for writing effective, maintainable tests.

### 1. Use Given-When-Then / Arrange-Act-Assert Pattern

Structure every test with clear sections for setup, action, and verification.

**Incorrect (Python):**

```python
def test_calculate_total():
    result = service.calculate_total([product1, product2])
    assert result == 150.0
    repository.find_all.assert_called_once()
```

**Correct (Python):**

```python
def test_calculate_total_valid_products_returns_sum():
    # Given
    product1 = Product("A", 50.0)
    product2 = Product("B", 100.0)
    repository.find_all.return_value = [product1, product2]

    # When
    actual_total = service.calculate_total()

    # Then
    expected_total = 150.0
    assert actual_total == expected_total
```

**Correct (Go):**

```go
func TestCalculateTotal_ValidProducts_ReturnsSum(t *testing.T) {
    // Given
    products := []Product{{Name: "A", Price: 50.0}, {Name: "B", Price: 100.0}}

    // When
    actualTotal := service.CalculateTotal(products)

    // Then
    expectedTotal := 150.0
    if actualTotal != expectedTotal {
        t.Errorf("got %v, want %v", actualTotal, expectedTotal)
    }
}
```

### 2. Use "actual" and "expected" Prefixes

Clearly distinguish between expected and actual values for better readability.

**Incorrect:**

```python
result = service.get_user(id)
assert result.name == name
```

**Correct:**

```python
actual_user = service.get_user(id)
expected_name = "John Doe"
assert actual_user.name == expected_name
```

### 3. Focus on Behavior, Not Implementation

Test externally visible effects, not internal implementation details.

**Incorrect:**

```python
# Testing implementation details
def test_calculate_total_uses_generator_expression():
    # verifying internal iteration strategy
    ...
```

**Correct:**

```python
# Testing behavior
def test_calculate_total_large_dataset_returns_correct_sum():
    # verifying the result, not how it's computed
    ...
```

### 4. Keep Tests Deterministic and Simple

Tests must produce the same result every time. Avoid business logic in tests.

**Incorrect:**

```python
def test_create_order_sets_timestamp():
    order = service.create_order()
    assert abs(order.timestamp - time.time()) < 1
```

**Correct (Python — inject a fixed clock):**

```python
def test_create_order_sets_timestamp():
    # Given
    fixed_clock = lambda: datetime(2024, 1, 1, tzinfo=timezone.utc)
    service = OrderService(clock=fixed_clock)

    # When
    actual_order = service.create_order()

    # Then
    assert actual_order.timestamp == datetime(2024, 1, 1, tzinfo=timezone.utc)
```

**Correct (JS/Jest — fake timers):**

```javascript
test('createOrder_setsTimestamp', () => {
  jest.useFakeTimers().setSystemTime(new Date('2024-01-01T00:00:00Z'));

  const actualOrder = service.createOrder();

  expect(actualOrder.timestamp).toEqual(new Date('2024-01-01T00:00:00Z'));
});
```

### 5. Verify Only Relevant Outputs and Interactions

Don't overuse mocks. Never mock the system under test or simple value objects.

**Incorrect:**

```python
# Over-mocking
def test_process_order():
    mock_product = Mock()
    mock_product.price = 100.0
    mock_product.name = "Test"
    # ...
```

**Correct:**

```python
# Use real objects for simple value objects
def test_process_order_valid_product_calculates_total():
    # Given
    product = Product("Test", 100.0)  # real object

    # When
    actual_result = service.process_order(product)

    # Then
    assert actual_result.total == 100.0
```

### 6. Use Helpers and Builders to Remove Duplication

Extract common setup logic into helper functions or builders.

**Incorrect:**

```python
def test_1():
    user = User()
    user.name = "John"
    user.email = "john@test.com"
    user.role = Role.ADMIN
    # ...

def test_2():
    user = User()
    user.name = "Jane"
    user.email = "jane@test.com"
    user.role = Role.USER
    # ...
```

**Correct:**

```python
def create_user(name, email, role):
    user = User()
    user.name = name
    user.email = email
    user.role = role
    return user

def test_1():
    user = create_user("John", "john@test.com", Role.ADMIN)
    # ...

def test_2():
    user = create_user("Jane", "jane@test.com", Role.USER)
    # ...
```
