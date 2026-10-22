---
title: Mocking in JavaScript / TypeScript
impact: HIGH
impactDescription: keeps mocking minimal, correctly hoisted, typed, and reset between tests in Jest and Vitest
tags: javascript, typescript, mocking, jest, vitest, msw, fake-timers
---

## Mocking in JavaScript / TypeScript

Mock only true externalities (`general-principles.md` rule #5). In JS/TS that means:

- HTTP: `fetch`, axios, generated API clients, third-party SDKs
- Database clients and ORMs: Prisma, Mongoose, Drizzle, TypeORM repositories, `pg`
- Filesystem, the clock, randomness and IDs (`Math.random`, `crypto.randomUUID`, `uuid`)
- `process.env`
- Framework runtime modules that don't exist in a test process: `next/navigation`, `next/headers` (see `frameworks/nextjs.md`)

Never mock the module under test, plain objects, DTOs, or a sibling pure-function module just because the target imports it.

Examples use Jest. In Vitest, `vi` replaces `jest` (`vi.fn`, `vi.mock`, `vi.spyOn`, `vi.mocked`, `vi.useFakeTimers`); the differences that matter are called out.

### 1. Prefer Injection Over Module Mocking

If the target receives its dependency as a parameter or constructor argument, pass a fake. No `jest.mock` is needed, and the fake is visible right where the test uses it.

```ts
import type { OrderRepository } from '../src/orders/order-repository';

function fakeRepository() {
  return {
    save: jest.fn(),
    findById: jest.fn(),
  } satisfies OrderRepository;
}

it('createOrder_validRequest_savesOnce', async () => {
  const repository = fakeRepository();
  repository.save.mockResolvedValue(undefined);
  const service = new OrderService(repository);

  await service.createOrder(buildOrderRequest());

  expect(repository.save).toHaveBeenCalledTimes(1);
});
```

`satisfies` checks the fake against the real interface without widening it, so `repository.save.mockResolvedValue` stays typed as a mock.

### 2. Module Mocks: `jest.mock` / `vi.mock`

Use these when the target imports its dependency directly.

```ts
import { sendEmail } from '../src/lib/mailer';
import { registerUser } from '../src/users/register-user';

jest.mock('../src/lib/mailer'); // automock: every export becomes a jest.fn()

const mockedSendEmail = jest.mocked(sendEmail);

beforeEach(() => {
  mockedSendEmail.mockResolvedValue({ messageId: 'msg-1' });
});
```

Rules that cause most mocking failures:

- **Mock calls are hoisted above the imports.** A factory can't reference variables from the test file. Jest allows names starting with `mock` (read lazily). Vitest needs `vi.hoisted`:

  ```ts
  const { mockSendEmail } = vi.hoisted(() => ({ mockSendEmail: vi.fn() }));
  vi.mock('../src/lib/mailer', () => ({ sendEmail: mockSendEmail }));
  ```

- **Mock the module the target actually imports.** The specifier must resolve to the same file. An alias (`@/lib/mailer`) and a relative path are the same module once resolved, but mocking `axios` does nothing if the target imports a configured instance from `../src/lib/http`. Mock that file instead.
- **Partial mocks keep the real exports you don't replace:**

  ```ts
  // Jest
  jest.mock('../src/lib/dates', () => ({
    ...jest.requireActual('../src/lib/dates'),
    now: jest.fn(),
  }));

  // Vitest
  vi.mock('../src/lib/dates', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../src/lib/dates')>();
    return { ...actual, now: vi.fn() };
  });
  ```

- **Native ESM under Jest** (`"type": "module"` and `--experimental-vm-modules`): `jest.mock` is not hoisted over ESM `import`s. Use `jest.unstable_mockModule(...)` and then `await import(...)` the target inside the test or a `beforeAll`. Check how existing tests do it first.
- **A default export** mocks as `{ __esModule: true, default: jest.fn() }`.

### 3. `spyOn` — Keep the Object, Watch or Replace One Method

```ts
const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
// ...
afterEach(() => { jest.restoreAllMocks(); });
```

Spying on an export of an ESM module fails with "Cannot redefine property" (the namespace object is frozen). Use a module mock instead.

### 4. HTTP

**If the repo already uses MSW** (`msw` in devDependencies with a `server` started in a setup file), use it: it intercepts at the network layer, so the target's real HTTP code runs. Match the installed major version:

```ts
// MSW v2
import { http, HttpResponse } from 'msw';
import { server } from '../test-utils/msw-server';

server.use(
  http.get('/api/orders/:id', () => HttpResponse.json({ id: 'ord-1', status: 'DRAFT' })),
);

// MSW v1: rest.get('/api/orders/:id', (req, res, ctx) => res(ctx.json({...})))
```

**Otherwise, mock the API-client module the target imports.** Failing that, mock `fetch`:

```ts
const fetchSpy = jest.spyOn(globalThis, 'fetch').mockResolvedValue(
  new Response(JSON.stringify({ id: 'ord-1' }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }),
);
```

`Response` and `fetch` are globals in Node 18+, but **Jest's jsdom environment doesn't provide them**. In a jsdom test, assign `globalThis.fetch = jest.fn()` and resolve it with a minimal object (`{ ok: true, status: 200, json: async () => ({ id: 'ord-1' }) }`), built in one typed helper. For axios, `jest.mock('axios')` and `jest.mocked(axios.get).mockResolvedValue({ data: {...} })`. Never let a test reach a real network.

Test the error paths too: a non-2xx `status` and a rejected `fetch` (a network failure) are different branches.

### 5. The Clock and Timers

```ts
beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date('2024-01-01T00:00:00Z'));
});
afterEach(() => {
  jest.useRealTimers();
});

it('scheduleReminder_after24Hours_sendsEmail', async () => {
  scheduleReminder(order);

  await jest.advanceTimersByTimeAsync(24 * 60 * 60 * 1000);

  expect(mockedSendEmail).toHaveBeenCalledTimes(1);
});
```

- Use the `...Async` advance functions (Jest 29.5+, Vitest) whenever the timer callback awaits anything. The synchronous versions fire the callback but not the promises it chains, and a test awaiting that work hangs.
- `jest.setSystemTime` fixes `Date.now()` and `new Date()`. If the target accepts a clock or `now` parameter, pass a fixed value instead and skip fake timers.
- Fake timers and React's user-event need wiring together; see `frameworks/react.md`.

### 6. Randomness and IDs

```ts
jest.spyOn(Math, 'random').mockReturnValue(0.42);
jest.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue('00000000-0000-4000-8000-000000000001');
jest.mock('uuid', () => ({ v4: () => '00000000-0000-4000-8000-000000000001' }));
```

Use the format the real function returns. A UUID mock returning `'abc'` can break code that validates IDs.

### 7. Environment Variables

A module that reads `process.env` at import time has to be imported again after the variable is set:

```ts
const ORIGINAL_ENV = process.env;

beforeEach(() => {
  jest.resetModules();
  process.env = { ...ORIGINAL_ENV };
});
afterEach(() => {
  process.env = ORIGINAL_ENV;
});

it('loadConfig_missingApiKey_throws', async () => {
  delete process.env.PAYMENTS_API_KEY;
  const { loadConfig } = await import('../src/config');

  expect(() => loadConfig()).toThrow('PAYMENTS_API_KEY is required');
});
```

Vitest: `vi.stubEnv('PAYMENTS_API_KEY', 'test-key')` with `vi.unstubAllEnvs()` in `afterEach`, plus `vi.resetModules()` for import-time reads.

### 8. Typed Mocks

- `jest.mocked(fn)` (Jest 27.4+) and `vi.mocked(fn)` turn an imported, module-mocked function into a typed mock. Use them instead of `fn as jest.Mock`.
- `jest.fn()`'s generic parameters differ between `@types/jest` and `@jest/globals`, and between Vitest 1 and 2+. Copy the form an existing test uses, or read the installed type definitions. Don't guess.
- Deep mocks of large clients (`mockDeep<PrismaClient>()` from `jest-mock-extended` / `vitest-mock-extended`) are fine **if the package is already installed**. Otherwise hand-build only the methods the target calls.
- No `as any` to make a mock fit. If it doesn't type-check, the mock's shape is wrong (see `typescript-in-tests.md`).

### 9. Verify Only Relevant Arguments

```ts
expect(mockedSendEmail).toHaveBeenCalledWith(
  'jane@example.com',
  expect.objectContaining({ template: 'welcome' }),
);
expect(repository.save).toHaveBeenCalledWith(expect.objectContaining({ status: 'CONFIRMED' }));
```

Use `expect.any(Date)`, `expect.any(String)` and `expect.objectContaining` for the parts this test doesn't own (`verify-relevant-arguments-only.md`).

### Checklist

- [ ] Only externalities are mocked; injected fakes are used where the target allows it
- [ ] Module mocks target the module the code actually imports; factories respect hoisting (`mock` prefix in Jest, `vi.hoisted` in Vitest)
- [ ] MSW is used if the repo has it; otherwise the API client or `fetch` is mocked, never the real network
- [ ] Fake timers use the `...Async` advance functions and are restored in `afterEach`
- [ ] `process.env` is copied and restored; import-time reads use `resetModules` and a dynamic `import()`
- [ ] Mocks are typed with `jest.mocked`/`vi.mocked` or `satisfies`, never `as any`
- [ ] Mock assertions check only the arguments this test is about
