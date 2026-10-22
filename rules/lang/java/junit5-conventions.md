---
title: JUnit 5 Conventions (Java)
impact: HIGH
impactDescription: keeps generated Java tests idiomatic JUnit Jupiter, consistent with the house style, and runnable by Surefire and Gradle
tags: java, junit5, junit-jupiter, parameterized-tests, nested, junit4
---

## JUnit 5 Conventions (Java)

Also read `rules/lang/jvm/jvm-build-and-location.md` (build, location, coverage). If the build only has JUnit 4, see §8.

### 1. Class and Method Shape

```java
package com.acme.orders;   // same package as OrderService

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class OrderServiceTest {

    private InMemoryOrderRepository repository;
    private OrderService orderService;

    @BeforeEach
    void setUp() {
        repository = new InMemoryOrderRepository();
        orderService = new OrderService(repository);
    }

    @Test
    void createOrder_validRequest_returnsDraftOrderWithTotal() {
        // Given
        CreateOrderRequest request = CreateOrderRequestTestData.aCreateOrderRequest()
                .withItem("A-100", 2, 500)
                .build();

        // When
        Order actualOrder = orderService.createOrder(request);

        // Then
        assertThat(actualOrder.status()).isEqualTo(OrderStatus.DRAFT);
        assertThat(actualOrder.totalCents()).isEqualTo(1000);
    }
}
```

- **Package-private class and methods.** No `public` is needed in JUnit 5. Match the house if it uses `public`.
- **Method names** follow the project format in camelCase: `createOrder_validRequest_returnsDraftOrderWithTotal`. Add `@DisplayName` only if existing tests use it.
- **A fresh instance per test.** JUnit 5 creates a new test-class instance per method, so plain fields set in `@BeforeEach` are safe. Never use `static` mutable fields shared between tests.
- **Given/When/Then** comments or blank-line separation, and `actual`/`expected` names (`general-principles.md`).
- Checked exceptions: declare `throws Exception` on the test method rather than catching.

### 2. Exceptions

`assertThrows` returns the exception. Assert on what matters about it (type, message, carried data). Don't stop at "something was thrown".

```java
@Test
void createOrder_emptyItems_throwsValidationExceptionAndSavesNothing() {
    CreateOrderRequest request = CreateOrderRequestTestData.aCreateOrderRequest().withNoItems().build();

    ValidationException actualException = assertThrows(ValidationException.class,
            () -> orderService.createOrder(request));

    assertThat(actualException).hasMessage("items must not be empty");
    assertThat(repository.findAll()).isEmpty();
}
```

With AssertJ, `assertThatThrownBy(() -> ...).isInstanceOf(ValidationException.class).hasMessage(...)` is equivalent. Use whichever the house uses. Keep the lambda to the **single call** under test, so setup that throws can't satisfy the assertion by accident.

### 3. Parameterised Tests

When cases differ only by data, use `@ParameterizedTest` (needs `junit-jupiter-params`, included in the `junit-jupiter` aggregate and in `spring-boot-starter-test`):

```java
@ParameterizedTest(name = "{0} tier → {1}")
@CsvSource({
        "STANDARD, 0.00",
        "PREMIUM,  0.15",
})
void calculateDiscount_byTier_returnsDocumentedRate(CustomerTier tier, BigDecimal expectedRate) {
    Customer customer = CustomerTestData.aCustomer().withTier(tier).build();

    BigDecimal actualRate = pricing.calculateDiscount(customer);

    assertThat(actualRate).isEqualByComparingTo(expectedRate);
}
```

| Source | Use for |
|---|---|
| `@CsvSource` | A few rows of simple values. Enums and numbers convert automatically |
| `@ValueSource` | One parameter, several values |
| `@EnumSource(value = OrderStatus.class, names = {"SHIPPED", "DELIVERED"})` | Behaviour shared by a subset of enum constants |
| `@NullAndEmptySource` / `@NullSource` / `@EmptySource` | Blank-input guards, combined with `@ValueSource(strings = {" "})` |
| `@MethodSource("invalidRequests")` | Rows that need real objects. The factory is a `static Stream<Arguments>` in the same class |

Expected values in rows are literals from the documented contract, never derived from the input (`no-logic-in-tests.md`). Don't parameterise cases that need different setup or different assertions. Those are separate tests.

### 4. Grouping with `@Nested`

When a class has several behaviours, group them with `@Nested` inner classes named after the behaviour (`test-behaviors-not-methods.md`):

```java
class OrderServiceTest {

    @Nested
    class CreateOrder {
        @Test
        void validRequest_returnsDraftOrder() { /* ... */ }

        @Test
        void emptyItems_throwsValidationException() { /* ... */ }
    }

    @Nested
    class CancelOrder {
        @Test
        void confirmedOrder_marksCancelled() { /* ... */ }
    }
}
```

`@Nested` classes are non-static inner classes, and they see the outer `@BeforeEach`. Use them when the house style does or when a class grows past a handful of tests; don't nest a class with three tests.

### 5. Lifecycle and Resources

- `@BeforeEach`/`@AfterEach` for per-test setup and cleanup. Use `@BeforeAll` (static) only for expensive, **immutable** setup.
- Files: `@TempDir Path workDir`. JUnit creates and deletes it. Never write inside the repository; an untracked file left behind fails the CI safety check.
- Timeouts: `assertTimeoutPreemptively` only when timing *is* the behaviour. Never use `Thread.sleep` to wait for something; inject a clock or an executor instead.

### 6. Tags and Disabled Tests

- Never add `@Disabled` to make a run green. A test you can't make pass is either removed (a test-writing mistake) or kept failing and flagged (a suspected bug), per generate-tests Step 12.
- Don't add `@Tag` unless the house uses tags to select suites. An unexpected tag can exclude the test from the build's default run.

### 7. Java Language Level

Use what the configured `release` allows, and what existing tests already use. `var` needs 10+, text blocks 15+, records 16+. Records in tests are fine for small value holders, but use the production type wherever one exists.

### 8. JUnit 4 Repositories

When the build has only `junit:junit`, write JUnit 4. Mixing in Jupiter annotations compiles but never runs:

| JUnit 5 | JUnit 4 |
|---|---|
| `org.junit.jupiter.api.Test` | `org.junit.Test` |
| `@BeforeEach` / `@AfterEach` | `@Before` / `@After` |
| `@BeforeAll` / `@AfterAll` | `@BeforeClass` / `@AfterClass` (static) |
| `@ExtendWith(MockitoExtension.class)` | `@RunWith(MockitoJUnitRunner.StrictStubs.class)` |
| `assertThrows` | `org.junit.Assert.assertThrows` (4.13+); never `@Test(expected = ...)`, which passes if *any* line throws |
| `@ParameterizedTest` | `@RunWith(Parameterized.class)`, or JUnitParams if installed |
| `@TempDir` | `@Rule public TemporaryFolder folder = new TemporaryFolder();` |

Classes and test methods must be `public` in JUnit 4.

### Checklist

- [ ] JUnit generation matches the build (5 by default, 4 only when that's all there is); no mixed annotations
- [ ] Class `<Class>Test`, same package; methods `method_state_outcome` in camelCase
- [ ] State rebuilt in `@BeforeEach`; no shared static mutable state
- [ ] Exceptions asserted with `assertThrows`/`assertThatThrownBy` around the single call under test, checking the message or data that matters
- [ ] Data-only variations use `@ParameterizedTest` with literal expected values
- [ ] Files go through `@TempDir`; no `Thread.sleep`, no `@Disabled`
