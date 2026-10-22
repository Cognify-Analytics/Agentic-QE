---
title: Testing Next.js Applications
impact: HIGH
impactDescription: unit-tests each kind of Next.js code (components, route handlers, server actions, middleware, data functions) through the seam that actually works for it
tags: nextjs, react, app-router, pages-router, route-handlers, server-actions, middleware
---

## Testing Next.js Applications

Read this when the stack has `next` in its dependencies. **Also read `frameworks/react.md`**, which covers every component test here. Next.js mixes code that runs in very different places (browser components, server components, HTTP handlers, edge middleware), and each one has a different unit-test seam.

### 1. Work Out What You're Dealing With

| Check | Why it matters |
|---|---|
| `app/` or `src/app/` exists | App Router: server components, route handlers, server actions |
| `pages/` or `src/pages/` exists | Pages Router: `getServerSideProps`, API routes, and **no tests inside `pages/`** (see `js-ts-test-location.md` §4) |
| `next` major version in `package.json` | **15+:** `params`, `searchParams`, `cookies()`, `headers()` and `draftMode()` are **Promises**. **14 and below:** plain values. Read the target's own type annotations, since passing the wrong one is the most common Next.js test bug |
| Runner config | `next/jest` (`createJestConfig`) already handles SWC, CSS/image/font mocks, `tsconfig` path aliases and `.env` loading. Vitest setups use `@vitejs/plugin-react`, and nothing is mocked for you |

### 2. Where Each Kind of Code Gets Tested

| Code | How to test it | Environment |
|---|---|---|
| Logic in `lib/`, `utils/`, `server/`, services | Plain unit tests; this is usually the highest-value target | `node` |
| Client components (`'use client'`) | RTL, per `frameworks/react.md` | `jsdom` |
| Synchronous Server Components | RTL `render(<Component />)`, like any component | `jsdom` |
| `async` Server Components | `render(await Page(props))` when its children are sync or client components; otherwise test the data functions it calls | `jsdom` |
| Route handlers (`app/**/route.ts`) | Call the exported `GET`/`POST`/… with a `Request`; assert on the `Response` | `node` |
| Server actions (`'use server'`) | Call the function directly with `FormData` or arguments | `node` |
| Middleware (`middleware.ts`, renamed `proxy.ts` in Next.js 16) | Call it with a `NextRequest`; assert on the returned response | `node` |
| `getServerSideProps` / `getStaticProps` | Call with a context object; assert on the returned `{ props }` / `{ notFound }` / `{ redirect }` | `node` |
| Pages API routes (`pages/api/*`) | Call `handler(req, res)` with fake `req`/`res` (`node-mocks-http` if installed) | `node` |

**Set the environment per file with a docblock** rather than editing config: `/** @jest-environment node */` or `// @vitest-environment node` for server code, `jsdom` for components. Jest's jsdom environment has no `Request`, `Response` or `Headers` globals, so importing `next/server` there fails before any test runs.

RTL can't render a tree with **nested** async Server Components. Don't fight it: test the data-loading functions directly, and record "async server component tree — covered via its data functions" in the notes. Next.js itself recommends end-to-end tests for that layer, and those are out of scope for v1.

### 3. Mocking Next.js Runtime Modules

These modules depend on a request context that doesn't exist in a unit test. Mock them, and **make `redirect()` and `notFound()` throw, as the real ones do**:

```ts
const mockPush = jest.fn(); // the "mock" prefix lets the hoisted factory read it

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn(), back: jest.fn(), refresh: jest.fn(), prefetch: jest.fn() }),
  usePathname: jest.fn(() => '/orders'),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  useParams: jest.fn(() => ({})),
  redirect: jest.fn((url: string) => { throw new Error(`NEXT_REDIRECT:${url}`); }),
  notFound: jest.fn(() => { throw new Error('NEXT_NOT_FOUND'); }),
}));
```

The real `redirect()` and `notFound()` throw to stop execution. A no-op mock lets the code after them run, so the test exercises a path production can never take and may assert on side effects that never happen.

| Module | Mock |
|---|---|
| `next/navigation` | As above. Assert navigation on the shared mock: `expect(mockPush).toHaveBeenCalledWith('/orders/ord-1')` (Vitest: create it with `vi.hoisted`) |
| `next/router` (Pages Router) | `useRouter` returning `{ push, query, pathname, asPath }`, or `next-router-mock` if installed |
| `next/headers` | 15+: `cookies: jest.fn(async () => ({ get: jest.fn((name: string) => (name === 'session' ? { name, value: 'sess-1' } : undefined)) }))`. 14: the same without `async` |
| `next/cache` | `{ revalidatePath: jest.fn(), revalidateTag: jest.fn(), unstable_cache: (fn: unknown) => fn }` |
| `server-only` | `jest.mock('server-only', () => ({}))`. The real package throws on import outside a React Server environment, which a test is |
| `next/font/google` (Vitest only) | `vi.mock('next/font/google', () => ({ Inter: () => ({ className: 'font-inter' }) }))`. `next/jest` already does this |

Mock only what the target imports. A component that only uses `usePathname` needs only that mock.

### 4. Route Handlers

```ts
/** @jest-environment node */
import { GET } from '@/app/api/orders/[id]/route';
import { getOrder } from '@/lib/orders';
import { buildOrder } from '../../test-utils/builders/order';

jest.mock('@/lib/orders');
const mockedGetOrder = jest.mocked(getOrder);

describe('GET /api/orders/[id]', () => {
  it('GET_existingOrder_returns200WithOrder', async () => {
    mockedGetOrder.mockResolvedValue(buildOrder({ id: 'ord-1', status: 'CONFIRMED' }));

    const actualResponse = await GET(new Request('http://localhost/api/orders/ord-1'), {
      params: Promise.resolve({ id: 'ord-1' }), // Next.js 15+; on 14 pass { id: 'ord-1' }
    });

    expect(actualResponse.status).toBe(200);
    expect(await actualResponse.json()).toEqual({
      id: 'ord-1',
      customerId: 'cust-1',
      items: [],
      status: 'CONFIRMED',
      totalCents: 0,
      createdAt: '2024-01-01T00:00:00.000Z',
    });
  });

  it('GET_unknownOrder_returns404', async () => {
    mockedGetOrder.mockResolvedValue(null);

    const actualResponse = await GET(new Request('http://localhost/api/orders/missing'), {
      params: Promise.resolve({ id: 'missing' }),
    });

    expect(actualResponse.status).toBe(404);
  });
});
```

- Use a plain `Request` unless the handler reads `NextRequest`-only fields (`nextUrl`, `cookies`). Then use `new NextRequest('http://localhost/...')` from `next/server`.
- For `POST`, use `new Request(url, { method: 'POST', body: JSON.stringify(payload), headers: { 'Content-Type': 'application/json' } })`, and cover the invalid-body branch.
- The expected JSON body is a literal (`json-serialization.md`). `Date` fields arrive as ISO strings, which is what a client really receives.

### 5. Server Actions

Server actions are async functions. Call them directly, mock the data layer, `next/cache` and `next/navigation`, and assert on the outcome: the return value, the redirect, the data written.

```ts
/** @jest-environment node */
import { createOrderAction } from '@/app/orders/actions';
import { db } from '@/lib/db';
import { revalidatePath } from 'next/cache';

jest.mock('@/lib/db', () => ({ db: { order: { create: jest.fn() } } }));
jest.mock('next/cache', () => ({ revalidatePath: jest.fn() }));
jest.mock('next/navigation', () => ({
  redirect: jest.fn((url: string) => { throw new Error(`NEXT_REDIRECT:${url}`); }),
}));

it('createOrderAction_validForm_savesAndRedirectsToNewOrder', async () => {
  jest.mocked(db.order.create).mockResolvedValue(buildOrder({ id: 'ord-9' }));
  const formData = new FormData();
  formData.set('sku', 'A-100');
  formData.set('quantity', '2');

  await expect(createOrderAction(formData)).rejects.toThrow('NEXT_REDIRECT:/orders/ord-9');

  expect(db.order.create).toHaveBeenCalledWith({
    data: expect.objectContaining({ sku: 'A-100', quantity: 2 }),
  });
  expect(revalidatePath).toHaveBeenCalledWith('/orders');
});
```

- Read the signature first. An action used with `useActionState` takes `(previousState, formData)`.
- Validation failures usually **return** an error object instead of throwing. Assert on that object, and assert that nothing was written (`expect(db.order.create).not.toHaveBeenCalled()`).
- Authorisation checks inside actions are a high-value branch. Cover the unauthenticated path via the mocked session/`cookies()`.

### 6. Middleware

```ts
/** @jest-environment node */
import { NextRequest } from 'next/server';
import { middleware } from '@/middleware';

it('middleware_noSessionCookie_redirectsToLogin', async () => {
  const request = new NextRequest('http://localhost/dashboard');

  const actualResponse = await middleware(request);

  expect(actualResponse?.status).toBe(307);
  expect(actualResponse?.headers.get('location')).toBe('http://localhost/login');
});
```

Set cookies on the request with `request.cookies.set('session', 'sess-1')`. The `matcher` in `config` is routing configuration, not logic. Test the function's decisions, not the matcher. On Next.js 15.1+, `next/experimental/testing/server` offers `unstable_doesMiddlewareMatch` and `getRedirectUrl` if you need them.

### 7. Pages Router Data Functions and API Routes

```ts
const actualResult = await getServerSideProps(buildGsspContext({ params: { id: 'missing' } }));

expect(actualResult).toEqual({ notFound: true });
```

Build the context in one typed helper (`buildGsspContext`) that casts once, per `typescript-in-tests.md` §2. For `pages/api` handlers, use `createMocks()` from `node-mocks-http` if installed. Otherwise build a minimal `res` whose `status()` returns `res` and whose `json()` records its argument.

### 8. Environment Variables

`NEXT_PUBLIC_*` values are inlined at build time, but in tests they're read from `process.env` at runtime. Set and restore them per `mocking-js-ts.md` §7. `next/jest` loads `.env.test` if present. Don't create or edit `.env*` files.

### Checklist

- [ ] Router type and `next` major version checked; Promise vs plain `params`/`cookies()` matches the target's types
- [ ] Server code tested in the `node` environment, components in `jsdom`, set per file with a docblock
- [ ] `redirect`/`notFound` mocks throw; only the `next/*` modules the target imports are mocked
- [ ] Route handlers called directly with `Request`; status and literal JSON body asserted
- [ ] Server actions called directly; return value, redirect, writes and `revalidatePath` asserted; auth branch covered
- [ ] Nested async server component trees covered via their data functions, noted rather than forced
- [ ] No test file inside `pages/`
