---
title: Testing Node.js Backends
impact: HIGH
impactDescription: unit-tests services, routes and middleware of Express, Fastify, NestJS, Koa and Hono apps in-process, without real ports, databases or files
tags: nodejs, express, fastify, nestjs, koa, hono, supertest, node-test, backend
---

## Testing Node.js Backends

Read this when the stack is a Node server or CLI: `express`, `fastify`, `@nestjs/core`, `koa` or `hono` in the dependencies, or a `server.ts`/`index.ts` that starts one. It builds on the rest of `rules/lang/javascript/`.

**Where the value is:** most bugs live in services and domain logic, not in route wiring. Test those first, with their dependencies injected. Then test the HTTP layer in-process, for status codes, validation and error mapping. Every test runs without a real port, database, queue or network. Anything that needs one is an integration test, which is out of scope for v1.

### 1. Services and Domain Logic

Construct the service with fakes for its collaborators (`mocking-js-ts.md` §1), and assert on the return value and on what it sent to collaborators:

```ts
it('refundOrder_alreadyRefunded_throwsConflictWithoutCallingPayments', async () => {
  const orders = { findById: jest.fn().mockResolvedValue(buildOrder({ status: 'REFUNDED' })), save: jest.fn() };
  const payments = { refund: jest.fn() };
  const service = new RefundService(orders, payments);

  await expect(service.refundOrder('ord-1')).rejects.toThrow(ConflictError);

  expect(payments.refund).not.toHaveBeenCalled();
});
```

### 2. The HTTP Layer, In-Process

Use the testing seam the framework provides, against the **app-building function** the repo exports. Never import a module that calls `listen()` at import time.

| Framework | Seam | Notes |
|---|---|---|
| Express | `supertest`: `await request(app).post('/orders').send(body)` | Only if `supertest` is installed. If the only export is a listening server, mount the real router on a fresh `express()` in the test instead |
| Fastify | `await app.inject({ method: 'POST', url: '/orders', payload: body })` | Built in. Build with the repo's `buildApp()`; `await app.close()` in `afterEach` |
| NestJS | `Test.createTestingModule({...}).compile()` | See §3 |
| Koa | `supertest` against `app.callback()` | |
| Hono | `await app.request('/orders', { method: 'POST', body: JSON.stringify(body) })` | Built in; returns a standard `Response` |

```ts
import request from 'supertest';
import { buildApp } from '../src/app';

it('POST_orders_emptyItems_returns400WithValidationMessage', async () => {
  const app = buildApp({ orderService: fakeOrderService() });

  const actualResponse = await request(app).post('/orders').send({ customerId: 'cust-1', items: [] });

  expect(actualResponse.status).toBe(400);
  expect(actualResponse.body).toEqual({ error: 'items must not be empty' });
});
```

Cover at least, per route: the success status and body, each validation failure, the not-found path, and how a thrown service error is mapped (status and body). **Express 4 does not catch rejected promises from `async` handlers** unless the repo wraps them (Express 5 does). If a service rejection hangs the request or crashes instead of returning 500, that's a real behaviour gap. Leave the test failing and flag it; don't adjust it.

### 3. NestJS

Follow the house style. Most NestJS repos use the testing module, which also proves the DI wiring resolves:

```ts
import { Test } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';

let service: OrdersService;
const ordersRepository = { findOneBy: jest.fn(), save: jest.fn() };

beforeEach(async () => {
  const moduleRef = await Test.createTestingModule({
    providers: [
      OrdersService,
      { provide: getRepositoryToken(Order), useValue: ordersRepository },
    ],
  }).compile();

  service = moduleRef.get(OrdersService);
});
```

- Provide fakes with the **same token** the service injects: the class, `getRepositoryToken(Entity)` (TypeORM), `getModelToken(Model.name)` (Mongoose), or a custom string/symbol token.
- Test a controller with the controller and a fake service in the module. Call its methods directly and assert on the return value and thrown `HttpException`s. Use `app.getHttpServer()` + `supertest` only when the repo already does, for pipes and guards.
- Test guards, pipes and interceptors as classes: construct them, call `canActivate`/`transform`/`intercept` with a minimal fake `ExecutionContext` built in one helper.

### 4. Middleware

Call the middleware as a function with fake `req`, `res` and `next`:

```ts
it('requireAuth_missingToken_responds401AndStops', () => {
  const req = fakeRequest({ headers: {} });
  const res = fakeResponse();
  const next = jest.fn();

  requireAuth(req, res, next);

  expect(res.status).toHaveBeenCalledWith(401);
  expect(next).not.toHaveBeenCalled();
});
```

Keep `fakeRequest`/`fakeResponse` in `test-utils/`. `res.status` and `res.json` are `jest.fn()`s that return `res`, so chained calls work. That helper is the one allowed cast (`typescript-in-tests.md` §2).

### 5. Databases and ORMs — Mock at the Client Boundary

| Client | Mock |
|---|---|
| Prisma | Mock the module that exports the client (`jest.mock('@/lib/prisma')`). Use `mockDeep<PrismaClient>()` if `jest-mock-extended`/`vitest-mock-extended` is installed; otherwise hand-build only the model methods used |
| Mongoose | `jest.spyOn(OrderModel, 'findById')`, returning **the same chain the code calls**: if it calls `.lean().exec()`, return `{ lean: () => ({ exec: async () => doc }) }` |
| TypeORM / MikroORM | Inject a fake repository (see §3) |
| `pg` / `mysql2` / Knex | Mock the module exporting the pool or query builder; assert on parameters, not on SQL whitespace |
| Redis, queues (BullMQ), S3, email, Stripe | Mock the module exporting the configured client |

Never open a real connection. If the repo already uses `mongodb-memory-server` or Testcontainers in unit tests, follow that house style. Otherwise treat a module that only works against a live database as untestable in isolation and skip it with a `skipped_reason`.

### 6. Filesystem

Prefer a real temporary directory over mocking `fs`. It's deterministic, cheap, and tests the real file handling:

```ts
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let workDir: string;
beforeEach(async () => { workDir = await mkdtemp(join(tmpdir(), 'qa-')); });
afterEach(async () => { await rm(workDir, { recursive: true, force: true }); });
```

**Never write inside the repository.** A file left behind is an untracked change, and the CI safety check fails the run on it. Use `memfs` only if it's already installed. Mock `fs` only when the target hard-codes a path you can't redirect.

### 7. Process-Level Behaviour

- **`process.exit`:** `jest.spyOn(process, 'exit').mockImplementation((() => { throw new Error('process.exit'); }) as never)`, then assert the call. Never let it really exit; that kills the test runner.
- **Logging:** don't assert on log lines unless logging *is* the behaviour (an audit log). Silencing a noisy logger with a spy is fine.
- **Signals, `child_process`, cron:** mock the module boundary (`child_process.spawn`, the scheduler) and test the decision logic, not the OS.

### 8. Node's Built-in Runner (`node:test`)

```ts
import { describe, it, beforeEach, mock } from 'node:test';
import assert from 'node:assert/strict';

describe('calculateTotal', () => {
  it('calculateTotal_twoItems_returnsSumInCents', () => {
    const actualTotal = calculateTotal([{ quantity: 2, unitPriceCents: 500 }, { quantity: 1, unitPriceCents: 250 }]);

    assert.equal(actualTotal, 1250);
  });

  it('chargeOrder_gatewayDown_rejectsWithPaymentError', async () => {
    const gateway = { charge: mock.fn(async () => { throw new Error('ECONNRESET'); }) };

    await assert.rejects(chargeOrder(gateway, buildOrder()), PaymentError);
    assert.equal(gateway.charge.mock.callCount(), 1);
  });
});
```

- Use `node:assert/strict` (`assert.equal` is then strict). `assert.deepEqual` for structures, `assert.rejects`/`assert.throws` for errors.
- `mock.fn()`, `mock.method(object, 'name')`, and `mock.timers.enable({ apis: ['setTimeout', 'Date'] })` for time. Call `mock.restoreAll()` in `afterEach`.
- Module mocking (`mock.module`) is experimental and behind a flag. Prefer injection.

### Checklist

- [ ] Services tested first, with injected fakes
- [ ] HTTP layer tested in-process through the framework's seam (`supertest`, `inject`, `app.request`, Nest testing module), never a real port
- [ ] Per route: success, each validation failure, not-found, and service-error mapping covered
- [ ] Fakes registered under the exact DI token the code injects (NestJS)
- [ ] ORM/DB/queue/SDK clients mocked at the module boundary, matching the real call chain; no real connections
- [ ] Filesystem tests use a temp dir and leave nothing inside the repo
- [ ] `process.exit` intercepted, never executed
