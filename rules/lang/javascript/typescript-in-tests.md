---
title: TypeScript in Tests
impact: HIGH
impactDescription: keeps tests type-checked against the real source types so they cannot invent fields or methods
tags: typescript, types, builders, ts-expect-error, path-aliases
---

## TypeScript in Tests

Tests are typed code. A test that only compiles because of `any` will happily call a method that doesn't exist or build an object with a misspelled field. That is the failure `code-context-analysis.md` exists to prevent. In a plain-JS repo, skip this file.

### 1. Import the Real Types; Never Redeclare Them

```ts
import type { Order, OrderStatus } from '@/types/order';
```

A shape copied into the test drifts from the source the first time someone adds a field. The test keeps passing against a type that no longer exists.

### 2. No `any`, No `as unknown as X` on Domain Data

If the compiler rejects your test data, the test is probably wrong about the shape. Go back and read the type (generate-tests Step 6). Don't silence the error.

**Incorrect:**

```ts
const order = { id: 1, state: 'confirmed' } as any; // wrong id type, wrong field name, wrong literal
```

**Correct:**

```ts
const order = buildOrder({ status: 'CONFIRMED' }); // typed builder, real field, real literal
```

The one allowed cast is at the boundary with a large framework object the target only partly uses (an Express `Request`, a Prisma client). Build just the fields the target touches and cast **once, inside a named helper**, never inline in each test:

```ts
// test-utils/http.ts
import type { Request } from 'express';

export function fakeRequest(fields: { params?: Record<string, string>; body?: unknown } = {}): Request {
  return { params: {}, body: undefined, ...fields } as unknown as Request;
}
```

### 3. Typed Builders with `Partial<T>` Overrides

```ts
// test-utils/builders/order.ts
import type { Order } from '@/types/order';

export function buildOrder(overrides: Partial<Order> = {}): Order {
  return {
    id: 'ord-1',
    customerId: 'cust-1',
    items: [],
    status: 'DRAFT',
    totalCents: 0,
    createdAt: new Date('2024-01-01T00:00:00Z'),
    ...overrides,
  };
}
```

The explicit `: Order` return type matters. When someone adds a required field to `Order`, the builder stops compiling, which tells you exactly where to update test data. Without the annotation it fails somewhere much less obvious. For nested objects, give each nested type its own builder rather than a `DeepPartial`.

Per `cleanly-create-test-data.md`, a test still passes any value its outcome depends on explicitly, even when the builder's default happens to match.

### 4. Invalid Input the Types Forbid: `@ts-expect-error`

Runtime guards exist for callers the compiler can't see (JSON bodies, plain-JS callers). Test them with `@ts-expect-error` and a reason, not `as any`:

```ts
it('createOrder_nullItems_throwsValidationError', () => {
  // @ts-expect-error -- runtime guard for untyped callers (JSON request bodies)
  expect(() => createOrder({ customerId: 'cust-1', items: null })).toThrow(ValidationError);
});
```

If the type is later widened to allow `null`, `@ts-expect-error` itself becomes an error, so the test stays honest. `as any` would hide that.

### 5. Literal Types and Enums

Use exactly what the type declares: the enum member (`OrderStatus.Confirmed`) or the union literal (`'CONFIRMED'`). A typo in a union literal is then a compile error rather than a test that asserts something impossible. Add `as const` to table rows (`it.each([...] as const)`) so literals aren't widened to `string`.

### 6. Path Aliases

Use the same import specifiers the source uses (`@/lib/pricing`). They only resolve in tests when the runner maps them: `moduleNameMapper` in Jest, `resolve.alias` or `vite-tsconfig-paths` in Vitest. `next/jest` maps `tsconfig` paths automatically. If existing tests use relative imports where the source uses aliases, assume the alias isn't mapped for tests and use relative paths too. Don't edit config to add a mapping.

### 7. Types of Mocks and Async Values

- `jest.mocked`/`vi.mocked` for module mocks and `satisfies Interface` for injected fakes (see `mocking-js-ts.md`).
- `mockResolvedValue(x)` must match the real return type's resolved value. `Awaited<ReturnType<typeof fn>>` names it when you need a typed constant.
- Don't annotate `actual*` variables. Let inference carry the real return type, so a wrong assertion (comparing a `number` to a `string`) is a compile error.

### 8. Type-Check Before Running

The compile phase for TypeScript is `tsc --noEmit`, filtered to the files you wrote (see `test-runner-conventions.md` §2). The runner usually strips types without checking them, so skipping this means type errors only show up as confusing runtime failures, or not at all.

### Checklist

- [ ] Types imported from source with `import type`, never redeclared
- [ ] No `any` or double casts on domain data; framework objects are cast once, in a named helper
- [ ] Builders return the real type explicitly and take `Partial<T>` overrides
- [ ] Invalid-input tests use `@ts-expect-error` with a reason
- [ ] Enum members / union literals as declared; table rows `as const`
- [ ] Import specifiers match the source's, or are relative when tests don't map aliases
- [ ] `tsc --noEmit` passes for every test file written
