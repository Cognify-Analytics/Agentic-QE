---
title: JavaScript / TypeScript Test Runner Conventions
impact: HIGH
impactDescription: picks the runner the repo actually uses (Jest, Vitest, node:test) and writes tests idiomatic to it
tags: javascript, typescript, jest, vitest, node-test, conventions, assertions
---

## JavaScript / TypeScript Test Runner Conventions

This folder covers JavaScript and TypeScript alike. Examples are TypeScript; in a plain-JS repo drop the type annotations and nothing else changes. Framework-specific rules (React, Next.js, Node backends) live in `frameworks/`.

### 1. Detect the Runner — Never Assume Jest

Read `package.json` (`scripts.test`, `devDependencies`) and look for a runner config. First match wins:

| Evidence | Runner |
|---|---|
| `vitest` in devDependencies, a `vitest.config.*`, or a `test` block in `vite.config.*` | Vitest |
| `jest` in devDependencies, a `jest.config.*`, a `"jest"` key in `package.json`, or `next/jest` in a config | Jest |
| `react-scripts test` in `scripts.test` | Jest, run through Create React App |
| `node --test` (or `tsx --test`) in `scripts.test`, and no Jest/Vitest | Node's built-in `node:test` |
| `mocha` (usually with `chai`) | Mocha — follow the existing tests' style; sections 3–7 still apply |

In a workspace monorepo (npm/pnpm/yarn workspaces, Turborepo, Nx) each package can have its own runner and config. Detect per package and run from that package's directory.

Use the package manager the lockfile names: `package-lock.json` → `npx`, `pnpm-lock.yaml` → `pnpm exec`, `yarn.lock` → `yarn`. The commands below use `npx`.

**Never introduce a second runner, and never edit configuration.** A Jest repo gets Jest tests even if Vitest would be nicer. `package.json`, `jest.config.*`, `vitest.config.*`, `vite.config.*`, `tsconfig*.json` and `babel.config.*` are not test files: the CI safety check fails any run that changes them, and configuration is the developer's decision. If the configuration makes a target untestable (for example, a component with no jsdom environment installed), skip the module with a `skipped_reason` naming exactly what is missing.

### 2. Commands — Run Once, Never Watch

`vitest` with no subcommand watches when it thinks it has a terminal; `react-scripts test` and many `"test": "jest --watch"` scripts watch too. A watching runner never exits, and the run hangs until it times out. Read `scripts.test` before reusing it.

| Runner | One file | Whole suite + coverage (the inventory's `test_command`) | Coverage report |
|---|---|---|---|
| Jest | `npx jest path/to/x.test.ts` | `npx jest --coverage --coverageReporters=cobertura --coverageReporters=text-summary` | `coverage/cobertura-coverage.xml` |
| Vitest | `npx vitest run path/to/x.test.ts` | `npx vitest run --coverage --coverage.reporter=cobertura --coverage.reporter=text-summary --coverage.reportOnFailure` | `coverage/cobertura-coverage.xml` |
| Create React App | `CI=true npx react-scripts test path/to/x` | `CI=true npx react-scripts test --coverage --coverageReporters=cobertura` | `coverage/cobertura-coverage.xml` |
| node:test | `node --test path/to/x.test.js` | `node --test --experimental-test-coverage --test-reporter=spec --test-reporter-destination=stdout --test-reporter=lcov --test-reporter-destination=lcov.info` | `lcov.info` |

- **The suite command must write coverage even when tests fail, and still exit non-zero.** Tests flagged as possible bugs are left failing on purpose, and `/triage-tests` decides "green suite" from the exit code. Jest writes coverage on failure by default; Vitest only does with `--coverage.reportOnFailure`. Never add anything that turns failures into a zero exit code.
- **Vitest coverage needs a provider package** (`@vitest/coverage-v8` or `@vitest/coverage-istanbul`). If neither is installed, run without `--coverage`, record coverage as `null` with a note, and do not install one. Jest's coverage is built in.
- **node:test with TypeScript** needs whatever loader `scripts.test` already uses (`tsx --test`, `node --import tsx --test`). Copy it rather than inventing one.
- Hand the report to `scripts/parse_coverage.py`, run from the repo root. It reads Cobertura and LCOV and resolves paths relative to the repo root.

**The compile phase (generate-tests Step 12) for TypeScript is a type-check.** Jest with Babel, `next/jest` (SWC) and Vitest (esbuild) all strip types without checking them, so a test that calls a method that doesn't exist still runs, and fails in a confusing way or passes for the wrong reason. Type-check before running:

```bash
npx tsc --noEmit -p tsconfig.json 2>&1 | grep -F "src/lib/pricing.test.ts"
```

- Use the tsconfig whose `include` covers the test file. If the main one excludes tests, look for `tsconfig.test.json` or `tsconfig.spec.json`.
- Only errors in files you wrote count. Pre-existing type errors elsewhere in the repo are not yours to fix and do not block. That is why the output is filtered to your file.
- `ts-jest` type-checks during the run; its diagnostics count as compile errors.
- Plain JavaScript has no compile phase. The run itself is the check, because syntax and import errors surface when the file loads.

### 3. Structure

- One `describe` per unit (module, class, function or component). Nest a `describe` per behaviour when a unit has several (see `test-behaviors-not-methods.md`). Use `it` or `test`, whichever the repo uses.
- Test names follow the project format, `{method}_{state}_{outcome}`. If the house style is sentences (`it('throws when items are empty')`), match it, but still name the state and the outcome.
- **Vitest:** import what you use (`import { describe, it, expect, vi, beforeEach } from 'vitest'`) unless the config sets `globals: true` and existing tests rely on globals. **Jest:** globals, or `@jest/globals` imports if the repo uses them (common in ESM projects).

```ts
import { describe, it, expect } from 'vitest';
import { createOrder } from '../src/orders/create-order';
import { buildOrderRequest } from '../test-utils/builders/order';

describe('createOrder', () => {
  it('createOrder_validRequest_returnsDraftOrderWithTotal', () => {
    // Given
    const request = buildOrderRequest({
      items: [{ sku: 'A', quantity: 2, unitPriceCents: 500 }],
    });

    // When
    const actualOrder = createOrder(request);

    // Then
    expect(actualOrder.status).toBe('DRAFT');
    expect(actualOrder.totalCents).toBe(1000);
  });
});
```

### 4. Assertions — Pick the Matcher That Fits the Value

| Need | Use | Not |
|---|---|---|
| Primitive equality | `toBe` | `toEqual` on a primitive (works, but not idiomatic) |
| Structural equality of objects/arrays | `toEqual`; `toStrictEqual` when `undefined` keys or the class matter | `toBe`, which compares references |
| Floating point | `toBeCloseTo(0.3, 5)` | `toBe(0.3)` |
| Only some fields matter | `toMatchObject({...})`, `expect.objectContaining({...})` | Asserting every field the test doesn't care about |
| Order-insensitive array | `expect.arrayContaining([...])` plus `toHaveLength(n)` | Sorting inside the test |
| Synchronous throw | `expect(() => fn()).toThrow(ValidationError)` or `.toThrow('items must not be empty')` | `try`/`catch` with an assertion in the catch |
| Rejected promise | `await expect(fn()).rejects.toThrow(NotFoundError)` | `.catch(...)` in the test |
| Absence | `toBeUndefined()`, `toBeNull()`, `not.toHaveBeenCalled()` | `toBeFalsy()` when `0`, `''` and `null` mean different things |

**A missing `await` makes the test pass vacuously.** `expect(promise).rejects.toThrow()` without `await` returns before the promise settles, so the test is green no matter what. Every `resolves`/`rejects` is awaited, and every async test is an `async` function.

### 5. Async Code

- Use `async`/`await`. Never return nothing from a test that starts a promise.
- Avoid `done` callbacks. For a callback API, wrap it in a promise in the test.
- Never wait with real time (`setTimeout`, sleeps). Use fake timers (`mocking-js-ts.md`) or, for UI, `findBy*`/`waitFor` (`frameworks/react.md`).
- A test that times out ("Exceeded timeout of 5000 ms") almost always has a promise nobody resolves: a mock that was never given a resolved value, or a fake timer never advanced. Fix the cause. Don't raise the timeout.

### 6. Table-Driven Cases: `it.each`

When cases differ only by input and expected value, use `it.each` with object rows. `$name` interpolation works in Jest 27+ and in Vitest.

```ts
it.each([
  { tier: 'STANDARD', expectedRate: 0 },
  { tier: 'PREMIUM', expectedRate: 0.15 },
] as const)('calculateDiscount_$tier-tier_returns-$expectedRate', ({ tier, expectedRate }) => {
  const customer = buildCustomer({ tier });

  const actualRate = calculateDiscount(customer);

  expect(actualRate).toBe(expectedRate);
});
```

`$name` keeps reading letters, digits, `_` and `.`, so `$tier_returns` looks up a field called `tier_returns` and prints `undefined`. End every `$name` with a `-`, a space or another non-word character.

The expected values are literals from the documented contract, never computed from the input (`no-logic-in-tests.md`).

### 7. Isolation

- Build the system under test and its fakes in `beforeEach` or in the test itself. Never share mutable module-level state between tests.
- **Reset mocks between tests.** If the config doesn't set `clearMocks`/`restoreMocks`, add `afterEach(() => { jest.clearAllMocks(); })` (Vitest: `vi.clearAllMocks()`), and also `jest.restoreAllMocks()` when the file used `spyOn`. Avoid `resetAllMocks` with factory mocks, because it also wipes their implementations.
- Restore anything global you changed: fake timers (`jest.useRealTimers()`), `process.env`, `globalThis.fetch`.
- Each test must pass alone and in any order. `npx jest -t 'name'` runs one test, and triage depends on that.

### 8. Snapshots — Not a Substitute for Assertions

A snapshot written by the first run records whatever the code currently does. That is the "assert the current output" anti-pattern this project exists to eliminate (PRD Section 1, Part 3).

- Don't generate snapshot tests to cover a module. Assert the specific, documented values instead.
- Use small `toMatchInlineSnapshot()` only when the repo already uses snapshots and the output is a stable serialisation the reader can check by eye.
- **Never run with `-u` / `--updateSnapshot`.** Rewriting a failing snapshot is the same as editing a failing assertion to match the code.

### Checklist

- [ ] Runner detected from `package.json`/config, not assumed; no second runner introduced
- [ ] No configuration file or `package.json` changed
- [ ] Commands run once (`vitest run`, `CI=true` for CRA), never watch mode
- [ ] TypeScript tests type-check with `tsc --noEmit`, judged on the files written only
- [ ] Every `resolves`/`rejects` and every async call is awaited
- [ ] Matchers fit the value (`toBe` vs `toEqual`, `toBeCloseTo` for floats)
- [ ] Mocks cleared and globals restored between tests
- [ ] No generated snapshots and no `--updateSnapshot`
