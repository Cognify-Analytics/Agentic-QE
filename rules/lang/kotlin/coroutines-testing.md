---
title: Testing Kotlin Coroutines and Flows
impact: HIGH
impactDescription: tests suspend functions, dispatchers and flows deterministically, in virtual time, without real delays or leaked coroutines
tags: kotlin, coroutines, runTest, flow, turbine, dispatchers, virtual-time
---

## Testing Kotlin Coroutines and Flows

Read this when the target has `suspend` functions, launches coroutines, or exposes `Flow`/`StateFlow`. It needs `kotlinx-coroutines-test` on the test classpath. Without it, `runBlocking { }` works for plain suspend calls that don't `delay` or launch background work. Note the gap, and skip time-dependent behaviour.

### 1. `runTest` — Virtual Time

```kotlin
@Test
fun retryPayment_gatewayFailsTwice_succeedsOnThirdAttempt() = runTest {
    // Given
    coEvery { gateway.charge(any()) } throws GatewayTimeoutException("t1") andThenThrows
        GatewayTimeoutException("t2") andThen ChargeResult.Accepted("ch-1")
    val service = PaymentService(gateway, retryDelay = 5.seconds)

    // When
    val actualResult = service.chargeWithRetry(aChargeRequest())

    // Then
    assertThat(actualResult).isEqualTo(ChargeResult.Accepted("ch-1"))
    assertThat(currentTime).isEqualTo(10_000)    // two 5-second back-offs, in virtual time
}
```

- `runTest` skips `delay`s by advancing a virtual clock. A test with a 5-second back-off finishes instantly, and `currentTime` shows how much virtual time passed. That's a precise way to assert on timeouts and back-off.
- The test function must **return** `runTest`'s result (`= runTest { }`). With Kotest, suspend test bodies work directly; use `runTest` inside them only when you need virtual time.
- Never `Thread.sleep`, and never wait on real time in a coroutine test.

### 2. Dispatchers — Inject Them

Virtual time only controls coroutines running on the test's scheduler:

- **The class takes a `CoroutineDispatcher` or `CoroutineScope`:** pass `StandardTestDispatcher(testScheduler)` (inside `runTest`), or `backgroundScope` for long-running collectors the test shouldn't wait for.
- **It hard-codes `Dispatchers.IO`/`Default`:** the work runs on real threads. `runTest` still waits for it, but `delay`s there take real time and ordering isn't controlled. Assert only on final results and note the coupling.
- **It uses `Dispatchers.Main`** (Android, UI-bound code): replace it for the test, and always restore it:

```kotlin
@BeforeEach
fun setUp() { Dispatchers.setMain(StandardTestDispatcher()) }

@AfterEach
fun tearDown() { Dispatchers.resetMain() }
```

### 3. Controlling Launched Work

With `StandardTestDispatcher`, launched coroutines don't run until the scheduler advances:

```kotlin
@Test
fun scheduleReminder_after24Hours_sendsEmail() = runTest {
    val scheduler = ReminderScheduler(mailer, scope = this)

    scheduler.scheduleReminder("ord-1")
    advanceTimeBy(24.hours - 1.milliseconds)
    coVerify(exactly = 0) { mailer.sendReminder(any()) }

    advanceUntilIdle()
    coVerify(exactly = 1) { mailer.sendReminder("ord-1") }
}
```

- `advanceTimeBy(d)` runs everything scheduled before `currentTime + d`. `advanceUntilIdle()` runs until nothing is left. `runCurrent()` runs what's due right now.
- Testing "nothing happened yet" before advancing is how you pin a delay. It's the coroutine equivalent of `toHaveBeenCalledTimes(0)` before advancing fake timers.
- An exception thrown in a launched child fails `runTest` at the end. Don't swallow it.

### 4. Flows

**Finite flows:** collect and compare.

```kotlin
@Test
fun orderEvents_confirmedOrder_emitsCreatedThenConfirmed() = runTest {
    val actualEvents = service.orderEvents("ord-1").toList()

    assertThat(actualEvents).containsExactly(OrderEvent.Created("ord-1"), OrderEvent.Confirmed("ord-1"))
}
```

`first()`, `take(n).toList()` and `single()` cover infinite or long flows when you only need the start.

**Hot flows (`StateFlow`, `SharedFlow`):** use Turbine if it's installed:

```kotlin
viewModel.state.test {
    assertThat(awaitItem()).isEqualTo(UiState.Loading)
    viewModel.load("ord-1")
    assertThat(awaitItem()).isEqualTo(UiState.Loaded(anOrder(id = "ord-1")))
    cancelAndIgnoreRemainingEvents()
}
```

Without Turbine, collect into a list in `backgroundScope` (it's cancelled automatically when the test ends), act, run `advanceUntilIdle()`, then assert on the list. A `StateFlow` conflates: rapid intermediate values can be skipped, so assert on the states the contract guarantees, not on every emission.

### 5. Exceptions from Suspend Functions

```kotlin
@Test
fun cancel_shippedOrder_throwsIllegalState() = runTest {
    coEvery { orders.findById("ord-1") } returns anOrder(id = "ord-1", status = OrderStatus.SHIPPED)

    val actualException = assertFailsWith<IllegalStateException> { service.cancel("ord-1") }

    assertThat(actualException.message).isEqualTo("order ord-1 is already shipped")
}
```

`assertFailsWith` (kotlin.test) and Kotest's `shouldThrow` are `inline`, so suspend calls work inside them under `runTest`.

**Cancellation is not an error.** Code that catches `Exception` and also swallows `CancellationException` is a real coroutine bug worth a test. Don't write tests that expect a `CancellationException` to be turned into a normal result.

### Checklist

- [ ] Suspend tests use `= runTest { }` (or Kotest suspend bodies); no `Thread.sleep`, no real waits
- [ ] Dispatchers injected where the code allows; `Dispatchers.setMain`/`resetMain` paired when `Main` is used
- [ ] Timing pinned with `advanceTimeBy` + "not yet" assertions, then `advanceUntilIdle`
- [ ] Finite flows collected with `toList()`; hot flows via Turbine or a `backgroundScope` collector
- [ ] Exceptions asserted with inline `assertFailsWith`/`shouldThrow`, checking the message
- [ ] MockK `coEvery`/`coVerify` for suspend collaborators
