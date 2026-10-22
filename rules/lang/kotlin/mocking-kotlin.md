---
title: Mocking in Kotlin (MockK, or Mockito with mockito-kotlin)
impact: HIGH
impactDescription: keeps Kotlin mocks strict, minimal and null-safe, and keeps global mocks from leaking between tests
tags: kotlin, mockk, mockito-kotlin, mocking, coroutines, slots
---

## Mocking in Kotlin

Same principle as every language (`general-principles.md` rule #5): mock repositories, clients, publishers and gateways. Never mock the class under test, data classes, value classes or sealed results; construct them (`kotlin-test-conventions.md` §5).

**Which library:** MockK if it's on the test classpath (idiomatic, and it handles final classes, `object`s and suspend functions). Otherwise Mockito with `mockito-kotlin` (§5).

### 1. MockK Basics

```kotlin
class RefundServiceTest {

    private val orders = mockk<OrderRepository>()
    private val payments = mockk<PaymentGateway>()
    private val service = RefundService(orders, payments)

    @Test
    fun refund_shippedOrder_refundsFullAmount() {
        // Given
        every { orders.findById("ord-1") } returns anOrder(id = "ord-1", status = OrderStatus.SHIPPED, totalCents = 1000)
        every { payments.refund(any()) } returns RefundResult.Accepted(refundId = "ref-1")

        // When
        service.refund("ord-1")

        // Then
        verify(exactly = 1) { payments.refund(RefundRequest(orderId = "ord-1", amountCents = 1000)) }
    }
}
```

- With JUnit 5, mocks declared as `private val` are new for every test, so no clearing is needed.
- **MockK mocks are strict:** calling anything that isn't stubbed throws `MockKException: no answer found for ...`. That means the test's setup doesn't match the code path. Read the code, then stub the call with its real arguments.
- **Avoid `mockk(relaxed = true)`.** It answers every call with a default and hides calls the test never considered. For collaborators that only return `Unit` (publishers, audit loggers), use `mockk<EventPublisher>(relaxUnitFun = true)` or `justRun { publisher.publish(any()) }`.

### 2. Stubbing Patterns

```kotlin
every { orders.findById("missing") } returns null
every { payments.refund(any()) } throws GatewayTimeoutException("timeout")
every { orders.save(any()) } answers { firstArg() }          // returns what it was given
every { idGenerator.next() } returnsMany listOf("ref-1", "ref-2")
```

Stub with exact values where you can. They catch wrong arguments, and `any()` doesn't. Use `match { it.amountCents == 1000 }` when only one property matters.

### 3. Verifying and Capturing

Verify only when the interaction **is** the behaviour (`verify-relevant-arguments-only.md`):

```kotlin
verify(exactly = 0) { payments.refund(any()) }       // must not refund on this path
verify { payments wasNot Called }                     // no interaction with the whole mock

val event = slot<OrderCancelled>()
every { publisher.publish(capture(event)) } just Runs
service.cancel("ord-1", reason = "customer request")
assertThat(event.captured.reason).isEqualTo("customer request")
```

Avoid `confirmVerified(...)` as a habit. Like Mockito's `verifyNoMoreInteractions`, it pins every call and breaks on harmless refactors.

### 4. Global Mocks: `object`s, Top-Level Functions, Statics — Last Resort

```kotlin
@AfterEach
fun tearDown() {
    unmockkAll()
}

@Test
fun createOrder_assignsGeneratedId() {
    mockkObject(IdGenerator)
    every { IdGenerator.next() } returns "ord-42"
    // ...
}
```

`mockkObject`, `mockkStatic("com.acme.util.TimeKt")` (top-level functions are statics on their file's `...Kt` class) and `mockkConstructor` change behaviour **for the whole JVM**. Always pair them with `unmockkAll()` in `@AfterEach`. Use them only when there's no injection seam (prefer an injected `Clock`/ID supplier), and note the coupling.

### 5. Mockito in Kotlin (No MockK)

Use `mockito-kotlin` if it's installed. Plain Mockito fights Kotlin in three ways:

| Problem | Plain Mockito | With mockito-kotlin |
|---|---|---|
| `when` is a Kotlin keyword | `` `when`(orders.findById("ord-1")).thenReturn(order) `` | `whenever(orders.findById("ord-1")).thenReturn(order)` |
| `Mockito.any()` returns `null` → NPE on non-null parameters | No clean fix | `any()`, `eq(...)`, `argumentCaptor<T>()` from `org.mockito.kotlin` |
| Kotlin classes are `final` | Needs the inline mock maker: default in Mockito 5, `mockito-inline` on 4 | Same |

```kotlin
private val orders: OrderRepository = mock()

whenever(orders.findById("ord-1")).thenReturn(anOrder(id = "ord-1"))
verify(payments).refund(RefundRequest(orderId = "ord-1", amountCents = 1000))
```

BDDMockito's `given(...).willReturn(...)` also avoids the backticks. Don't add `mockito-extensions/org.mockito.plugins.MockMaker` to enable inline mocking; that's shared test config (`jvm-build-and-location.md` §4).

### 6. Suspend Functions

MockK has coroutine-aware variants. Use them for every `suspend` function:

```kotlin
coEvery { orders.findById("ord-1") } returns anOrder(id = "ord-1")
coJustRun { publisher.publish(any()) }
coVerify(exactly = 1) { payments.refund(any()) }
```

Calling `every { }` on a suspend function doesn't compile. Running tests that use these is covered in `coroutines-testing.md`. With Mockito, `mockito-kotlin`'s `onBlocking { findById("ord-1") } doReturn order` / `verifyBlocking(...)` are the equivalents.

### Checklist

- [ ] MockK used when available; otherwise Mockito via `mockito-kotlin` (`whenever`, Kotlin-safe matchers)
- [ ] Only collaborators mocked; data classes and results constructed
- [ ] No `relaxed = true`; `relaxUnitFun`/`justRun` only for `Unit`-returning collaborators
- [ ] Stubs use exact values; verification only where the interaction is the behaviour; slots for built arguments
- [ ] `mockkObject`/`mockkStatic`/`mockkConstructor` only as a last resort, always with `unmockkAll()` in `@AfterEach`
- [ ] `coEvery`/`coVerify`/`coJustRun` for every suspend function
