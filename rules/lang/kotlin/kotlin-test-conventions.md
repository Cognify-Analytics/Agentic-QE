---
title: Kotlin Test Conventions (JUnit 5 and Kotest)
impact: HIGH
impactDescription: keeps generated Kotlin tests idiomatic to the framework the repo uses, with null-safe, data-class-based test data
tags: kotlin, junit5, kotest, kotlin-test, data-classes, nullability
---

## Kotlin Test Conventions

Also read `rules/lang/jvm/jvm-build-and-location.md` (build, location, coverage). Mocking is in `mocking-kotlin.md`, coroutines in `coroutines-testing.md`. Where the Java rules and these differ, these win for Kotlin code.

### 1. Detect the Framework

| Test dependency | Framework | Write |
|---|---|---|
| `kotest-runner-junit5` | Kotest | Specs in the house style (§4) |
| `junit-jupiter`, `kotlin("test")` / `kotlin-test-junit5` | JUnit 5 | Annotated test classes (§2) |
| Only `junit:junit` | JUnit 4 | `org.junit.Test`, `@Before` (see the JUnit 4 table in `rules/lang/java/junit5-conventions.md` §8) |

Assertions follow the classpath and the neighbouring tests: Kotest matchers (`shouldBe`), AssertJ, `kotlin.test` (`assertEquals(expected, actual)`), assertk or Strikt. Use one style per file. Never add a library to the build.

### 2. JUnit 5 in Kotlin

```kotlin
package com.acme.pricing

import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import kotlin.test.assertFailsWith

class DiscountPolicyTest {

    private val policy = DiscountPolicy()

    @Test
    fun calculateDiscount_premiumTier_returnsDocumentedRate() {
        // Given
        val customer = aCustomer(tier = CustomerTier.PREMIUM)

        // When
        val actualRate = policy.calculateDiscount(customer)

        // Then
        assertThat(actualRate).isEqualByComparingTo("0.15")
    }

    @Test
    fun calculateDiscount_suspendedCustomer_throwsIneligible() {
        val customer = aCustomer(status = CustomerStatus.SUSPENDED)

        val actualException = assertFailsWith<IneligibleCustomerException> {
            policy.calculateDiscount(customer)
        }

        assertThat(actualException.message).isEqualTo("customer cust-1 is suspended")
    }
}
```

- **Names:** the project format, as a plain identifier: `calculateDiscount_premiumTier_returnsDocumentedRate`. Use backtick sentences (``fun `returns 15 percent for premium customers`()``) only when the house style does, and still name the state and the outcome.
- **Fresh state per test:** JUnit 5 creates a new instance per test method, so `private val` properties initialised inline are fresh for every test. There's no need for `lateinit` + `@BeforeEach` unless setup needs to be shared logic.
- **Exceptions:** `assertFailsWith<T> { ... }` (kotlin.test) or `assertThrows<T> { ... }` (JUnit's Kotlin extension). Both return the exception, so assert the message or data. Keep the lambda to the single call under test.
- **`@BeforeAll` and `@MethodSource`** need static members. Put them in a `companion object` with `@JvmStatic`, or annotate the class `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` when the house does:

```kotlin
@ParameterizedTest(name = "{0} tier → {1}")
@MethodSource("ratesByTier")
fun calculateDiscount_byTier_returnsDocumentedRate(tier: CustomerTier, expectedRate: String) {
    val actualRate = policy.calculateDiscount(aCustomer(tier = tier))

    assertThat(actualRate).isEqualByComparingTo(expectedRate)
}

companion object {
    @JvmStatic
    fun ratesByTier() = listOf(
        Arguments.of(CustomerTier.STANDARD, "0.00"),
        Arguments.of(CustomerTier.PREMIUM, "0.15"),
    )
}
```

### 3. Null Safety, Sealed Types and `Result`

- **Test the null branches the types allow.** A `String?` parameter is a documented input, so cover it. A non-null parameter is the compiler's job. Don't force `null` into it through Java interop or reflection.
- **Never use `!!` in a test.** It turns a failed expectation into a `NullPointerException` with no context. Use `assertNotNull(actual)` (kotlin.test) or `actual.shouldNotBeNull()` (Kotest); both smart-cast for the following lines.
- **Sealed hierarchies:** assert the subtype, then its data. `assertIs<PaymentResult.Declined>(actualResult)` (kotlin.test, smart-casts) or `actualResult.shouldBeInstanceOf<PaymentResult.Declined>()`, followed by `assertThat(actualResult.reason)...`.
- **`Result<T>`:** `assertThat(actual.exceptionOrNull()).isInstanceOf(...)`, or Kotest's `shouldBeFailure<T>()`. Never `getOrThrow()` in a test that expects a failure.

### 4. Kotest

Match the spec style existing tests use. With Kotest present and no tests yet, use `FunSpec`:

```kotlin
class DiscountPolicyTest : FunSpec({

    test("calculateDiscount_premiumTier_returnsDocumentedRate") {
        val policy = DiscountPolicy()

        val actualRate = policy.calculateDiscount(aCustomer(tier = CustomerTier.PREMIUM))

        actualRate shouldBe BigDecimal("0.15")
    }
})
```

- **Isolation:** Kotest's default isolation mode runs every test in a spec against **one shared instance**. State declared in the spec body leaks between tests. Create the class under test and its fakes **inside each test**, or reset them in `beforeTest { clearAllMocks() }`. Don't rely on a fresh instance the way JUnit 5 gives you.
- **Naming under Maven:** Surefire only runs classes matching `*Test`/`Test*`/`*Tests`/`*TestCase`, so a Kotest class named `DiscountPolicySpec` never runs under Maven unless the pom configures includes. Use `*Test` in Maven builds unless existing specs prove otherwise.
- **`BigDecimal` with `shouldBe`** compares scale too (`0.15` ≠ `0.150`). Use `shouldBeEqualComparingTo` or build the expected value with the same scale the contract states.
- **Exceptions:** `shouldThrow<IneligibleCustomerException> { ... }`, which returns the exception.
- **Data-driven tests:** `withData(...)` if it resolves, either from the `kotest-framework-datatest` module or built into newer Kotest versions. Otherwise write separate tests.

### 5. Test Data: Factory Functions with Default Arguments

Kotlin doesn't need builder classes. A top-level factory with named, defaulted parameters gives the same readability:

```kotlin
// src/test/kotlin/com/acme/testdata/OrderTestData.kt
package com.acme.testdata

fun anOrder(
    id: String = "ord-1",
    customerId: String = "cust-1",
    status: OrderStatus = OrderStatus.DRAFT,
    items: List<OrderItem> = emptyList(),
    createdAt: Instant = Instant.parse("2024-01-01T00:00:00Z"),
) = Order(id = id, customerId = customerId, status = status, items = items, createdAt = createdAt)

fun anOrderItem(sku: String = "A-100", quantity: Int = 1, unitPriceCents: Long = 500) =
    OrderItem(sku = sku, quantity = quantity, unitPriceCents = unitPriceCents)
```

- Call with **named arguments**, overriding only what the scenario is about (`anOrder(status = OrderStatus.CONFIRMED)`), and always passing the values the test asserts on.
- The factory calls the real constructor, so a new required property breaks it in one place.
- `copy()` derives a variant of an existing object in the test: `order.copy(status = OrderStatus.CANCELLED)`.
- Same fixed-literal rules as Java: `Instant.parse`, `BigDecimal("19.99")` from strings, readable IDs (`rules/lang/java/java-test-data.md` §5).

### 6. Kotlin-Specific Pitfalls

- **`internal` declarations** are visible to tests in the same module; test them as public API. Don't test `private` functions through reflection.
- **`object` singletons and top-level `var`s** keep state across tests in the same JVM. If the code under test mutates one, reset it in `@AfterEach`, or note the coupling and skip.
- **Extension functions** are tested by calling them on a real receiver.
- **Default arguments in production functions** are behaviour too. A call that omits an argument tests the default. Cover it when the default is the documented contract.

### Checklist

- [ ] Framework (JUnit 5 / Kotest / JUnit 4) and assertion style match the build and neighbouring tests
- [ ] Names follow `method_state_outcome` (backtick sentences only if the house uses them)
- [ ] JUnit 5: inline `val` properties for fresh state; `@MethodSource` factories in a `companion object` with `@JvmStatic`
- [ ] Kotest: state created per test or reset in `beforeTest`; class named `*Test` under Maven
- [ ] No `!!`; nullable inputs covered; sealed results asserted by subtype, then data
- [ ] Test data via default-argument factory functions and named arguments
