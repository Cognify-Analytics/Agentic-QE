---
title: Test Data in Java
impact: MEDIUM
impactDescription: builds readable, compile-safe test objects with builders and factories instead of long constructor calls and reflection
tags: java, test-data, builders, object-mother, records, lombok
---

## Test Data in Java

`cleanly-create-test-data.md` sets the principle: hide what's irrelevant, show what the test depends on. In Java the usual tools are a **test data builder** for objects with many fields, and **static factory methods** for common named cases.

### 1. Reuse Before Writing

Look first for existing builders and fixtures. Search `src/test` (and `src/testFixtures`) for `*TestData`, `*Builder`, `*Fixtures`, `*Mother`, `a*()`/`an*()` factory methods. Add to what's there, in its style. Never create a second builder for the same type.

### 2. Test Data Builder

```java
package com.acme.orders.testdata;

public final class OrderTestData {

    private String id = "ord-1";
    private String customerId = "cust-1";
    private OrderStatus status = OrderStatus.DRAFT;
    private List<OrderItem> items = new ArrayList<>();
    private Instant createdAt = Instant.parse("2024-01-01T00:00:00Z");

    private OrderTestData() {
    }

    public static OrderTestData anOrder() {
        return new OrderTestData();
    }

    public static OrderTestData aConfirmedOrder() {
        return anOrder().withStatus(OrderStatus.CONFIRMED);
    }

    public OrderTestData withId(String id) {
        this.id = id;
        return this;
    }

    public OrderTestData withStatus(OrderStatus status) {
        this.status = status;
        return this;
    }

    public OrderTestData withItem(String sku, int quantity, long unitPriceCents) {
        this.items.add(new OrderItem(sku, quantity, unitPriceCents));
        return this;
    }

    public Order build() {
        return new Order(id, customerId, status, List.copyOf(items), createdAt);
    }
}
```

- **`build()` calls the real constructor or factory.** When production adds a required field, the builder stops compiling in one place, instead of every test breaking.
- **Defaults are valid and boring.** The builder produces an object that passes validation, and the test overrides only what its scenario is about.
- **Tests still set what they assert on**, even when it equals the default: `anOrder().withStatus(OrderStatus.DRAFT)` in a test about drafts.
- **Never set fields by reflection** to build test data. If the only way to get an object into a state is through its public operations, use them (`order.confirm()`), which also tests the state transition is reachable.
- Put builders in a `testdata` package under the module's test base package, or wherever existing builders live. They're test code, so `src/test/...` (or `src/testFixtures/...` when the build applies `java-test-fixtures`).

### 3. When the Production Type Already Has a Builder

- **Lombok `@Builder`** (or a hand-written builder) on the production class: use it. `Order.builder().id("ord-1")...build()`. Wrap it in a factory method that fills in valid defaults (`OrderTestData.anOrder()` returning a pre-filled `Order.OrderBuilder`), and use `toBuilder()` if it's enabled.
- **Records with few components:** a `static` factory with the varying parts as parameters is enough. A full builder is overkill for three fields.

### 4. Large Payloads

Big JSON/CSV/XML samples go in `src/test/resources/<subject>/` and are loaded via the classpath:

```java
String body = new String(getClass().getResourceAsStream("/orders/create-order-request.json").readAllBytes(), UTF_8);
```

Only use files for genuinely large or externally-sourced payloads (a sample webhook). Keep small expected JSON inline as a text block, next to the assertion it supports.

### 5. Dates, Money and IDs

- Fixed `Instant.parse(...)`/`LocalDate.of(...)` literals, never `now()`.
- `BigDecimal` from strings (`new BigDecimal("19.99")`), never from doubles (`new BigDecimal(19.99)` is `19.989999...`).
- IDs as readable literals (`"ord-1"`, a fixed UUID string), not `UUID.randomUUID()`, so a failure message is reproducible.

### Checklist

- [ ] Existing builders/factories searched for and extended, not duplicated
- [ ] Builders call the real constructor/factory; defaults are valid; no reflection
- [ ] Tests set every value they assert on explicitly
- [ ] Production builders (Lombok, records) reused through test factories
- [ ] Large payloads in `src/test/resources`; small JSON inline
- [ ] Dates, money and IDs are fixed literals (`BigDecimal` from strings)
