---
title: Mocking in Java (Mockito)
impact: HIGH
impactDescription: keeps Mockito use minimal, strict and readable, so that tests fail for behavioural reasons rather than stubbing noise
tags: java, mockito, mocking, argument-captor, strict-stubs, mockstatic
---

## Mocking in Java (Mockito)

Mock only true externalities (`general-principles.md` rule #5): repositories and DAOs, HTTP and SDK clients, message publishers, the clock, ID generators, and other services behind an interface. **Never mock** the class under test, records, DTOs, entities, value objects, collections or `String`s. Build real ones (`java-test-data.md`).

### 1. Setup: Strict Stubs by Default

```java
@ExtendWith(MockitoExtension.class)
class RefundServiceTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private PaymentGateway paymentGateway;

    private RefundService refundService;

    @BeforeEach
    void setUp() {
        refundService = new RefundService(orderRepository, paymentGateway);
    }
}
```

`MockitoExtension` (from `mockito-junit-jupiter`) uses **strict stubs**: a stub the test never uses fails with `UnnecessaryStubbingException`, and a stub called with different arguments fails with `PotentialStubbingProblem`. Both are useful signals:

- **Unnecessary stubbing:** the stub is noise for this scenario. **Remove it.** Don't reach for `lenient()` or `@MockitoSettings(strictness = LENIENT)` to quiet it.
- **Potential stubbing problem:** the code called the collaborator with arguments the test didn't expect. Read the code. Either the stub's arguments are wrong (a test mistake) or the code passes the wrong value, which may be a real bug. Don't loosen the stub to `any()` just to make it pass.

If `mockito-junit-jupiter` isn't on the classpath, create mocks with `Mockito.mock(OrderRepository.class)` in `@BeforeEach`.

### 2. Constructing the Class Under Test

Prefer calling the constructor yourself (as above): it's explicit, and it fails at compile time when a dependency is added. Use `@InjectMocks` only for field-injected classes or when the house uses it. Note that it **silently leaves a dependency `null`** when it can't match one, which turns a setup gap into a confusing `NullPointerException` later.

### 3. Stubbing

```java
given(orderRepository.findById("ord-1")).willReturn(Optional.of(shippedOrder));   // BDD style
when(orderRepository.findById("ord-1")).thenReturn(Optional.of(shippedOrder));    // classic style
```

- Use the style existing tests use; BDDMockito (`given`/`willReturn`/`then`) reads naturally with Given/When/Then.
- **Stub only what this scenario's code path calls**, with the exact arguments it passes.
- Throwing: `given(paymentGateway.refund(any())).willThrow(new GatewayTimeoutException("timeout"))`. For `void` methods: `willThrow(...).given(publisher).publish(any())` or `doThrow(...).when(publisher).publish(any())`.
- Returning the argument (a `save` that returns what it got): `given(orderRepository.save(any(Order.class))).willAnswer(invocation -> invocation.getArgument(0))`.
- Unstubbed methods return empty values (`null`, `0`, `false`, empty collections, `Optional.empty()`). A test that relies on that default for its outcome should stub it explicitly (`cleanly-create-test-data.md`: never rely on defaults).

### 4. Argument Matchers — All or Nothing

If any argument uses a matcher, **all** of them must:

```java
given(pricing.priceFor(eq("A-100"), anyInt())).willReturn(500);   // correct
given(pricing.priceFor("A-100", anyInt())).willReturn(500);       // InvalidUseOfMatchersException
```

Prefer real values over matchers in stubs, since precise stubs catch wrong arguments. Use `any(Order.class)` rather than raw `any()` when overloads exist.

### 5. Verifying Interactions

Verify interactions only when the interaction **is** the behaviour: a payment made, an event published, a save that must or must not happen. Don't verify calls whose effect is already visible in the returned value.

```java
then(paymentGateway).should().refund(refundRequestFor("ord-1", 1000));
then(paymentGateway).shouldHaveNoInteractions();         // refund must not happen on this path
then(orderRepository).should(never()).save(any());
```

When the argument is built inside the method, capture it and assert only the fields this test is about (`verify-relevant-arguments-only.md`):

```java
@Captor
private ArgumentCaptor<OrderCancelledEvent> eventCaptor;

@Test
void cancel_confirmedOrder_publishesCancelledEventWithReason() {
    given(orderRepository.findById("ord-1")).willReturn(Optional.of(OrderTestData.aConfirmedOrder().withId("ord-1").build()));

    orderService.cancel("ord-1", "customer request");

    then(eventPublisher).should().publish(eventCaptor.capture());
    assertThat(eventCaptor.getValue().reason()).isEqualTo("customer request");
}
```

Avoid `verifyNoMoreInteractions` as a habit. It pins every call the implementation makes and breaks on harmless refactors.

### 6. Time, IDs and Static Calls

- **Clock:** if the class takes a `java.time.Clock`, pass `Clock.fixed(Instant.parse("2024-01-01T00:00:00Z"), ZoneOffset.UTC)`. Don't mock `Clock`.
- **IDs:** if IDs come from an injected `Supplier<UUID>`/`IdGenerator`, stub it with a fixed UUID literal.
- **Static calls** (`LocalDateTime.now()`, `UUID.randomUUID()`) with no seam: as a last resort, use `mockStatic` in try-with-resources so the stub cannot leak into other tests:

  ```java
  try (MockedStatic<UUID> uuid = mockStatic(UUID.class)) {
      uuid.when(UUID::randomUUID).thenReturn(UUID.fromString("00000000-0000-4000-8000-000000000001"));
      // when + then inside the block
  }
  ```

  Mockito 5 has the inline mock maker by default (static and final mocking work). On Mockito 4 or older, this needs `mockito-inline`. If it's absent, assert on what doesn't depend on the value instead, and say so.

### 7. Final Classes and Types You Don't Own

Mockito 5 mocks final classes. Even so, **don't mock third-party types** with wide, unstable APIs (an AWS SDK client, `RestTemplate`, `JdbcTemplate`, `HttpClient`). Mock the repo's own wrapper or port around them one level up. If the class under test uses the third-party type directly with no wrapper, mock it narrowly, stubbing only the calls the code makes, and note the coupling.

### 8. Spies — Rarely

`@Spy` on a real object partially mocks it. Spying on the **class under test** to stub one of its own methods is testing the implementation, not the behaviour. Don't. A spy is acceptable for a real collaborator whose one method needs overriding, but a hand-written fake is usually clearer.

### Checklist

- [ ] Only externalities mocked; value objects, DTOs, records and entities are real
- [ ] `MockitoExtension` strict stubs kept; unused stubs removed, never made lenient
- [ ] Class under test built via its constructor (or `@InjectMocks` with every dependency present)
- [ ] Stubs use exact values; matchers are all-or-nothing; no `any()` added just to get past a mismatch
- [ ] Interactions verified only when they are the behaviour; captors check only relevant fields
- [ ] `Clock`/ID suppliers injected with fixed values; `mockStatic` only as a scoped last resort
