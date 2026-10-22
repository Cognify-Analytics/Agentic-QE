---
title: JavaScript / TypeScript Test Location
impact: HIGH
impactDescription: puts tests where the runner will actually find them, without turning helpers into broken suites or tests into Next.js routes
tags: javascript, typescript, test-location, jest, vitest, nextjs
---

## JavaScript / TypeScript Test Location

`rules/test-location-map.md` decides the order: **the repo's existing convention always wins**, and the default below only applies when the repo has no tests at all. This file adds what's specific to JS/TS. There are several common conventions, and a file the runner doesn't match never runs.

### 1. Find the Existing Convention, and What the Runner Matches

Look for existing tests (`**/__tests__/**`, `**/*.test.*`, `**/*.spec.*`, a top-level `test/` or `tests/`), then read what the runner collects:

- **Jest:** `testMatch` / `testRegex` / `roots` in the config. The default `testMatch` is every `.js/.jsx/.ts/.tsx` file inside a `__tests__` folder, plus any `*.test.*` or `*.spec.*` file.
- **Vitest:** `test.include`. The default is `**/*.{test,spec}.?(c|m)[jt]s?(x)`. Files inside `__tests__/` are **not** collected unless they have a `.test`/`.spec` suffix.

A new test must match the runner's pattern. Check before writing, not after a run reports "no tests found".

| House style found | New test for `src/lib/pricing.ts` goes to |
|---|---|
| Co-located `*.test.ts` | `src/lib/pricing.test.ts` |
| `__tests__/` beside the source | `src/lib/__tests__/pricing.test.ts` |
| Root `__tests__/` mirroring the source tree | `__tests__/lib/pricing.test.ts` |
| Root `test/` or `tests/` | `tests/lib/pricing.test.ts` |

Match the house suffix too (`.test` vs `.spec`).

### 2. No Tests Yet: the Default

Use a root-level `__tests__/` folder mirroring the source tree under `src/` (or under the package root if there is no `src/`), with a `.test` suffix:

```
src/lib/pricing.ts              → __tests__/lib/pricing.test.ts
src/components/OrderForm.tsx    → __tests__/components/OrderForm.test.tsx
app/api/orders/route.ts         → __tests__/app/api/orders/route.test.ts
```

- **Always add the `.test` suffix**, even inside `__tests__/`. Jest collects either way; Vitest only collects files with the suffix.
- `.test.tsx` when the file contains JSX, `.test.ts` otherwise. In a JS repo use `.test.js`/`.test.jsx`, and `.test.mjs` if the source uses `.mjs`.
- This default works for every runner and is the one layout that is always safe in Next.js (see §4).

### 3. Helpers and Builders Must Not Look Like Test Suites

**Jest treats every file in a `__tests__/` folder as a test suite.** A builder at `__tests__/builders/order.ts` gets collected, contains no tests, and fails the run with "Your test suite must contain at least one test."

Put shared helpers where the runner won't collect them and the CI safety check still recognises them as test code:

```
test-utils/builders/order.ts      ← typed builders (see typescript-in-tests.md)
test-utils/render.tsx             ← custom RTL render with providers (see frameworks/react.md)
test-utils/msw-server.ts          ← MSW server, if the repo uses MSW
```

- Reuse an existing helpers folder if the repo has one (`test-utils/`, `test/helpers/`, `src/test-utils.tsx`). Add to it rather than creating a parallel one.
- A file named `test-utils.ts(x)` or `testUtils.ts` is recognised as test code wherever it lives. Any other non-test name inside `src/` (for example `src/mocks/handlers.ts`) is treated as production source and **fails the CI safety check**.
- Jest manual mocks live in `__mocks__/` next to the module they replace (or at the root for `node_modules` packages). Only add one when the repo already uses manual mocks; otherwise use a factory in the test file.

### 4. Next.js: Never Put a Test Inside `pages/`

- **Pages Router:** every file under `pages/` becomes a route and is built for production. `pages/orders.test.tsx` breaks `next build` unless `next.config` restricts `pageExtensions`. Put tests for pages in the root `__tests__/pages/...` mirror.
- **App Router:** only the special files (`page`, `layout`, `route`, `loading`, `error`, …) are routes, and folders starting with `_` are private. A co-located `page.test.tsx` or an `app/orders/__tests__/` folder is safe, but use them only when that's the house style.

### 5. Setup Files

Never create a new setup file (`jest.setup.ts`, `vitest.setup.ts`, `setupTests.ts`). It only runs if the config references it, and config is off-limits. Use what the existing setup file provides. If a test needs `@testing-library/jest-dom` matchers and no setup file imports them, import them at the top of that test file (`import '@testing-library/jest-dom'`, or `'@testing-library/jest-dom/vitest'` under Vitest), but only if the package is installed.

### 6. Monorepos

A test belongs to the workspace package that owns the source, inside that package's own test location, run with that package's runner from that package's directory. Never import another package's source through a relative path like `../../other-package/src`. Use its package name, as the source does.

### Checklist

- [ ] Existing location and suffix matched; the default is used only when no tests exist
- [ ] The new file matches the runner's `testMatch`/`include`
- [ ] Every test file carries a `.test`/`.spec` suffix
- [ ] Helpers and builders live in `test-utils/` (or the repo's existing helpers folder), never in Jest's `__tests__/` and never under a production-looking name in `src/`
- [ ] No test inside a Next.js `pages/` directory
- [ ] No new setup file, no config change
