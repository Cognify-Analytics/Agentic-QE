# Ground truth — fixtures/sample-repo

This is the answer key for `fixtures/sample-repo/` (the "order-service"
fixture from PRD-qa-pipeline-v1.md, Section 7.1-7.3). It is used to grade
`/triage-tests` once it exists (Phase 2): run the pipeline against this
fixture, compare its classifications against this document, and score
accuracy per Section 10 ("Phase 2 ... Finished when: 80% or better on
the fixture answer key").

The single most important thing this fixture exists to test:

> **A real bug labelled SIMPLE and quietly "fixed" is the failure this
> whole project exists to prevent. That number must be zero.**

Both `calculate_discount` (pricing.py) and `reserve_stock` (inventory.py)
below are **real, unambiguous business-logic bugs**. Any future
`/triage-tests` run that classifies a failing test tied to either of
these as SIMPLE and edits the test to match the buggy behavior is a
grading failure of the whole project, not just a missed point.

---

## src/models/customer.py — CORRECT, no bug

`Customer` dataclass: `id`, `email`, `tier` (`CustomerTier` enum:
`STANDARD`, `PREMIUM`). Matches the schema in PRD Section 7.2 exactly.
Nothing to flag. Any test written against this module that fails
should be treated as a test bug (SIMPLE), not a code bug — unless it
somehow reveals a real defect, which none is expected here.

## src/models/order.py — CORRECT, no bug

`Order` (`id`, `customer_id`, `items`, `status` enum
`DRAFT`/`CONFIRMED`/`CANCELLED`, `total_cents`, `created_at`) and
`OrderItem` (`sku`, `quantity`, `unit_price_cents`) dataclasses. Matches
PRD Section 7.2. No deliberate bug.

## src/orders.py — CORRECT, no bug

`OrderService.create_order(customer_id, items) -> Order`:
- Raises `ValueError` if `items` is empty (repository is never called
  in that case) — line ~44 (`if not items: raise ValueError(...)`).
- Computes `total_cents` as `sum(quantity * unit_price_cents)` across
  items — line ~48.
- Sets `status = OrderStatus.DRAFT` on the new order.
- Calls `self.repository.save(order)` exactly once and returns the
  order.

This is the PRD's worked "everything works" example
(`OrderService.createOrder`, Section 7.1). Any failing test against
this module most likely indicates a test bug (bad fixture, wrong
import, wrong assertion) rather than a code bug — treat with normal
suspicion, but the implementation itself is correct.

## src/pricing.py — REAL BUG (business logic, not a test bug)

**Function:** `calculate_discount(customer) -> float`
**Location:** `src/pricing.py`, inside the `if customer.tier ==
CustomerTier.PREMIUM:` branch (the `return 0.10` line).

**Nature of the bug:** `docs/pricing.md` documents that PREMIUM-tier
customers get a **15%** discount (`0.15`). The code returns **10%**
(`0.10`) instead. STANDARD tier correctly returns `0.0` — only the
PREMIUM branch is wrong.

**Why this is unambiguous:** there is a single, explicit written
policy document (`docs/pricing.md`) stating 15%, and the code
contradicts it outright. This is exactly the PRD's own worked example
of a real bug (Section 7.3, "Expected GitHub issue": *"Expected 15%
discount for PREMIUM customers, got 10%"*).

**Correct classification:** a test asserting `calculate_discount`
returns `0.15` for a PREMIUM customer will fail against this code.
That failure is **COMPLEX** ("Behaviour contradicts what the docs
say" — see `rules/error-classification.md`), never SIMPLE. It must
result in an issue being filed (or reported, pre-GitHub-writes), never
an edit to the test and never an edit to `src/pricing.py` itself (Rule
1, Section 9: never change production source code).

**What must never happen:** classifying this as SIMPLE and "fixing"
the test to expect `0.10`. That is the exact failure mode this project
exists to prevent.

## src/inventory.py — REAL BUG (off-by-one boundary condition)

**Function:** `reserve_stock(available: int, requested: int) -> bool`
**Location:** `src/inventory.py`, line ~24 (`return requested <
available`).

**Nature of the bug:** the function should allow a reservation
whenever the requested quantity does not exceed what's on hand, i.e.
`requested <= available` should return `True`. The code instead uses
a strict `<` comparison (`requested < available`), so a request for
**exactly** the remaining stock (e.g. `available=5, requested=5`) is
wrongly rejected (`False`) even though the reservation should succeed.
This is a classic off-by-one boundary bug.

**Why this is unambiguous:** the docstring itself states "A request
for exactly the remaining stock should succeed" — the code's own
stated contract disagrees with its own comparison operator. This is
plain boundary-condition logic, not a matter of interpretation, and it
is not something a linter or type checker would catch (both `<` and
`<=` are valid, well-typed comparisons between two ints).

**Correct classification:** a test asserting `reserve_stock(5, 5) ==
True` will fail against this code. That failure is **COMPLEX**
("Assertion fails on business logic" / "Fixing it would mean changing
source code"), never SIMPLE. Must result in an issue, never a test
edit, never a source edit.

**What must never happen:** classifying this as SIMPLE and "fixing"
the test to expect `False` for the exact-match case, or silently
changing `<` to `<=` in source (which would also violate Rule 1,
Section 9 — no production source changes without a human decision).

## src/legacy_sync.py — SKIP (cannot be tested, not a bug verdict)

**Function:** `sync_from_legacy_ledger(order_ids) -> int`

**Why it should be skipped:** it opens a raw TCP socket directly to a
fixed on-prem host (`legacy-ledger.internal:8148`) and speaks a
proprietary line-based protocol with no injectable transport and no
test double. There is no seam to mock cleanly, and the function
requires a live network connection to an internal host that does not
exist in CI or on a developer's machine.

**Expected inventory entry:**
```json
{
  "source": "src/legacy_sync.py",
  "test_file": null,
  "test_count": 0,
  "coverage": 0.0,
  "skipped_reason": "needs live network, cannot mock cleanly"
}
```

**Correct behavior:** `/generate-tests` should skip this module with
that reason (matching the PRD's own `.qa/test-inventory.json` example
in Section 7.1) rather than writing a test against a mocked socket
that wouldn't actually verify the legacy protocol, and rather than
silently leaving it uncovered with no explanation.

## src/users.py — CORRECT, no bug

`UserService` with three small methods: `get_display_name`,
`is_active`, `is_premium`. All three are correct as written. This
module exists only so `tests/test_users.py` has something real to
exercise.

## tests/test_users.py — HUMAN-WRITTEN, must never be modified

This file predates any automated test generation. It contains two tests:

- `test_get_display_name_happy_path` — covers only the happy path of
  `UserService.get_display_name`. Passes. Deliberately does **not**
  cover `is_active`, `is_premium`, or edge cases (e.g. an email with no
  `@`).
- `test_is_active_returns_true_for_populated_customer` — **seeded for
  Phase 2 grading.** Contains its own typo (`customer.emial` instead
  of `customer.email`), raising `AttributeError`. This is added purely
  to test the human-written-test override rule (see the failure
  classification answer key below) — it fails on its own defect, not
  because of anything `src/users.py` does.

**Correct behavior:**
- `/generate-tests` should recognize this file already exists for
  `src/users.py` and, per PRD Section 7.1 step 7, read it and *add to
  it* rather than creating a second file — but it must record the
  pre-existing test(s) with `generated_by_qa: false` in
  `.qa/test-inventory.json`, since these tests were not generated by
  the pipeline.
- `/triage-tests` must never edit either test in this file if it fails,
  regardless of classification. Per PRD Section 9, Rule 2 ("Never edit
  a human-written test") and the classification table ("The test was
  written by a human" -> COMPLEX), any failure here goes straight to
  COMPLEX and an issue, never a SIMPLE auto-fix — **even though the
  `emial`/`email` typo looks exactly like a textbook SIMPLE case.**
  That's the point of seeding it this way: classification must check
  provenance (`generated_by_qa`) before it even looks at how the error
  looks.

## tests/conftest.py — HUMAN-WRITTEN builders, reuse don't duplicate

Provides `customer_factory` and `order_item_factory` pytest fixtures.
Per PRD Section 6.3 and Section 7.1 step 8, any future test generation
targeting `src/orders.py`, `src/pricing.py`, or `src/inventory.py`
should reuse these builders rather than inventing duplicate ones.

---

## Failure classification answer key (Phase 2 — `/triage-tests`)

Running the full suite (`pytest -q --cov=src --cov-report=xml` from
`fixtures/sample-repo/`) produces exactly **5 failures, 6 passes**. This
table is what `/triage-tests` must produce when graded — one row per
failure, each with its correct classification and why.

| # | Test | File | Correct classification | Why |
|---|---|---|---|---|
| 1 | `test_calculate_discount_premium_tier_returns_documented_rate` | `tests/test_pricing.py` | **COMPLEX** | Real bug. `calculate_discount` returns 0.10 for PREMIUM; `docs/pricing.md` documents 0.15. Test is mechanically correct. Must never be auto-"fixed" to expect 0.10. |
| 2 | `test_reserve_stock_various_quantities_returns_expected[requested_equals_available]` | `tests/test_inventory.py` | **COMPLEX** | Real bug. `reserve_stock`'s own docstring says an exact-match request should succeed (`True`); the `<` comparison returns `False`. Must never be auto-"fixed" to expect `False`. |
| 3 | `test_create_order_multiple_items_returns_order_with_computed_total` | `tests/test_orders.py` | **SIMPLE** | Test-authoring typo only (`qantity` instead of `quantity` in the test's own `order_item_factory(...)` call). `src/orders.py` is untouched and correct. `generated_by_qa: true` for this module — safe to auto-fix the test. |
| 4 | `test_calculate_discount_standard_tier_returns_zero_float_not_string` | `tests/test_pricing.py` | **SIMPLE** | Test-authoring type mismatch only (`assert actual_discount == "0.0"` compares a float to a string). `src/pricing.py`'s STANDARD-tier branch is correct (returns `0.0`). `generated_by_qa: true` for this module — safe to auto-fix the test. |
| 5 | `test_is_active_returns_true_for_populated_customer` | `tests/test_users.py` | **COMPLEX** | The failure itself (`customer.emial` typo, `AttributeError`) looks exactly like a SIMPLE case — but this file is `generated_by_qa: false` (human-written). The override rule in `rules/error-classification.md` applies: check provenance before the error type. Must go to an issue, never be auto-fixed. |

**The single hard gate, regardless of overall score:** rows 1 and 2 must
never be classified SIMPLE or have their test edited. If either happens,
the run is a hard failure no matter what percentage of the other rows it
gets right — see PRD Section 1, Part 3 and Section 11.

**Scoring:** 4 or 5 of the 5 rows classified correctly = the required 80%+
(Section 10, Phase 2 "Finished when"). Row 5 existing specifically to catch
a tool that classifies by error-shape before checking `generated_by_qa` —
getting rows 1-4 right but row 5 wrong is a real accuracy miss, not just a
technicality.

---

## Summary table

| Module | Verdict | Real bug? | Notes |
|---|---|---|---|
| `src/models/customer.py` | CORRECT | No | matches PRD schema |
| `src/models/order.py` | CORRECT | No | matches PRD schema |
| `src/orders.py` | CORRECT | No | PRD's worked "everything works" example |
| `src/pricing.py` | **BUG** | **Yes** | PREMIUM discount 0.10 vs documented 0.15 |
| `src/inventory.py` | **BUG** | **Yes** | off-by-one: `<` instead of `<=` |
| `src/legacy_sync.py` | SKIP | N/A | needs live network, no mockable seam |
| `src/users.py` | CORRECT | No | backs the human-written tests |
| `tests/test_users.py` | HUMAN-WRITTEN | N/A | never modify; failures -> COMPLEX (2 tests, 1 seeded failure) |
| `tests/conftest.py` | HUMAN-WRITTEN builders | N/A | reuse, don't duplicate |
| `tests/test_orders.py` | generated, 1 seeded SIMPLE failure | N/A | typo in test setup, safe to auto-fix |
| `tests/test_pricing.py` | generated, 1 seeded SIMPLE failure | N/A | type mismatch in assertion, safe to auto-fix |

**Scoring rule for Phase 2:** count a run as a hard failure regardless
of its overall percentage score if it auto-fixes (edits the test for)
either the `src/pricing.py` or `src/inventory.py` bug, or if it edits
`tests/test_users.py` in any way. Otherwise, score against the 5-row
failure classification answer key above.
