---
title: Assertions in Java Tests
impact: HIGH
impactDescription: uses the assertion library already on the classpath, with the comparison that matches the value (BigDecimal, collections, Optional, records)
tags: java, assertj, assertions, hamcrest, junit-assertions, bigdecimal
---

## Assertions in Java Tests

### 1. Which Library

| On the test classpath | Use |
|---|---|
| AssertJ (`assertj-core`, included in `spring-boot-starter-test`) | AssertJ: `assertThat(actual).isEqualTo(expected)` |
| Only JUnit | `org.junit.jupiter.api.Assertions` (`assertEquals(expected, actual)`; **expected first**) |
| Hamcrest, used by existing tests | Hamcrest, to match the house |

Use one library per test class, and match the neighbours. Never add AssertJ to the build to use it.

### 2. Equality and Its Traps

| Value | Use | Not |
|---|---|---|
| `BigDecimal` | `assertThat(actual).isEqualByComparingTo("15.00")` | `isEqualTo(new BigDecimal("15"))`, which fails on scale (`15.00` vs `15`) |
| `double`/`float` | `isCloseTo(0.15, within(1e-9))` | `isEqualTo(0.15)` after arithmetic |
| Records, value objects with `equals` | `isEqualTo(expectedOrder)` | Field-by-field when `equals` already defines the contract |
| Entities/DTOs without a meaningful `equals` | `usingRecursiveComparison().ignoringFields("id", "createdAt").isEqualTo(expected)` | `isEqualTo` (reference equality); ignoring more fields than the test can't control |
| `Optional` | `assertThat(actual).contains(expected)`, `.isEmpty()` | `actual.get()`, which throws instead of failing clearly |
| `Instant`/`LocalDateTime` | Exact equality with a fixed clock | `isCloseTo(now, ...)` against the real clock |
| `String` | `isEqualTo`, `startsWith`, `contains`, `matches` | `contains` when the exact value is the documented contract |

### 3. Collections

```java
assertThat(actualOrders)
        .extracting(Order::id)
        .containsExactly("ord-1", "ord-2");          // order matters

assertThat(actualSkus).containsExactlyInAnyOrder("A-100", "B-200");   // order doesn't
assertThat(actualOrders).hasSize(2);
assertThat(actualOrders).isEmpty();
assertThat(actualOrders).singleElement().extracting(Order::status).isEqualTo(OrderStatus.DRAFT);
```

- Prefer `containsExactly`/`containsExactlyInAnyOrder` over `contains`. `contains` passes when extra, unexpected elements are present.
- `extracting(...)` keeps the assertion on the field that matters, with a readable failure message, instead of a loop or a stream in the test (`no-logic-in-tests.md`).
- Maps: `containsEntry("A-100", 2)`, `containsOnlyKeys(...)`.

### 4. Exceptions

```java
assertThatThrownBy(() -> orderService.cancel("ord-1"))
        .isInstanceOf(IllegalStateException.class)
        .hasMessage("order ord-1 is already shipped");

assertThatNoException().isThrownBy(() -> orderService.cancel("ord-2"));
```

Use `hasMessage` (exact) when the message is part of the contract (API error bodies, documented errors), and `hasMessageContaining` when only part of it is. Assert the cause with `hasRootCauseInstanceOf(...)` when wrapping is the behaviour.

### 5. Several Facts About One Result

Several `assertThat` lines on one result are fine; the first failure stops the test. When every mismatch matters at once (a mapped DTO, for example), use soft assertions:

```java
assertSoftly(softly -> {
    softly.assertThat(actualDto.id()).isEqualTo("ord-1");
    softly.assertThat(actualDto.status()).isEqualTo("CONFIRMED");
    softly.assertThat(actualDto.totalCents()).isEqualTo(1000);
});
```

(JUnit-only: `assertAll(() -> assertEquals(...), ...)`.) Keep them to **one scenario**; soft assertions aren't a licence to test three behaviours in one method (`keep-tests-focused.md`).

### 6. JSON

For JSON output, compare against a literal with JSONassert (`JSONAssert.assertEquals(expectedJson, actualJson, JSONCompareMode.STRICT)`), `JsonPath`, or `JacksonTester` (Spring). Never serialise an expected object with the same `ObjectMapper` the code uses (`json-serialization.md`).

### 7. Messages

AssertJ's failure messages are already descriptive. Add `.as("...")` only when the value alone doesn't explain what was being checked. It goes **before** the assertion: `assertThat(x).as("premium discount").isEqualByComparingTo("0.15")`.

### Checklist

- [ ] The library on the classpath and in neighbouring tests is used; nothing added to the build
- [ ] `BigDecimal` compared with `isEqualByComparingTo`; floating point with a tolerance
- [ ] Objects without `equals` compared recursively, ignoring only uncontrollable fields
- [ ] Collections asserted with `containsExactly`/`containsExactlyInAnyOrder` and `extracting`
- [ ] Exceptions assert type **and** the contract-relevant message
- [ ] JSON compared to literals, never re-serialised expectations
