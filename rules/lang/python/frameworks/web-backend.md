---
title: Testing Python Web Backends
impact: HIGH
impactDescription: tests FastAPI, Starlette, Flask and Django apps through their routes and middleware in-process, with the database, external APIs and heavy libraries faked at the module's own seams
tags: python, fastapi, starlette, flask, django, testclient, backend, routes, middleware, auth
---

## Testing Python Web Backends

Read this when a Python stack depends on `fastapi`, `starlette`, `flask` or `django`. It builds on the rest of `rules/lang/python/`.

**Where the value is:** in the HTTP layer as much as in the helpers. Auth middleware that blocks a path meant to be public, a route that turns a 400 into a 500, a credential the code documents but never reads: none of these show up in tests that call helper functions directly, and they are among the most valuable things this pipeline finds. So **a web module is not covered until its routes are tested through the framework's test client.** Helpers get direct tests too, but they are where the job starts, not where it ends.

A large single-file app (one 3,000-line `main.py` with fifty routes) is one module in the inventory and dozens of behaviours in practice. Plan the tests per route (§5), not per file.

Every test runs in-process: no real port, database, network, model download, or file outside a temp dir.

### 1. Build the App Without Its Side Effects

| Framework | Client | Watch out for |
|---|---|---|
| FastAPI, Starlette | `TestClient(app)` from `fastapi.testclient` (needs `httpx`) | `with TestClient(app):` runs the `startup`/`lifespan` hooks: DB init, seeding, model warm-up. Use the bare client unless the test is about startup |
| Flask | `app.test_client()`; with an app factory, `create_app(...)` with the repo's test config | A factory that connects to the database while building the app, with no way to override it |
| Django | `django.test.Client`, DRF's `APIClient`, or `RequestFactory` to call one view directly | Anything that touches the ORM (§9) |

If the module does work at import time, such as reading env vars or opening a pool, make the import safe first. Set the env vars it reads at the top of `conftest.py`, before the import (`os.environ.setdefault("DATABASE_URL", "")`). Then check it really imports: `python -c "import main"` from the stack's folder (`generate-tests` Step 5a).

`TestClient` needs `httpx`. If `httpx` is missing, record a tooling gap (`generate-tests` Step 13a) and still test what you can: FastAPI route functions are ordinary functions, so call them directly with their dependencies passed in. Don't skip the stack.

### 2. Pin Configuration, Per Test

Settings read once at import (`SECRET_KEY = os.getenv(...)`) don't change when the environment does later. Patch the module's attributes instead, in one autouse fixture in `conftest.py`, so every test starts from the same known state:

```python
@pytest.fixture(autouse=True)
def isolated_app(monkeypatch, tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(main, "APP_SECRET_KEY", "test-secret")
    monkeypatch.setattr(main, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(main, "PAYMENTS_API_KEY", None)
    monkeypatch.setattr(main, "_PROFILE_CACHE", {})   # module-level caches start empty
    monkeypatch.setattr(main, "_jobs", {})            # and so do job registries
```

- Point every directory the app writes to at `tmp_path`. A file left in the repo is an untracked change, and the CI safety check fails the run on it.
- Reset module-level caches and registries. A test that only passes after another test has filled a cache will fail when the order changes.
- For FastAPI settings injected with `Depends(get_settings)`, override the dependency instead (§3).

### 3. Fake the Database at the Module's Own Seam

Find the narrowest functions every query goes through and replace those, not the driver:

| What the code does | Replace |
|---|---|
| Calls its own data helpers (`_db_select`, `run_query`, a `repository` module) | Those helpers: `monkeypatch.setattr(main, "_db_select", fake_db.select)` |
| Uses FastAPI `Depends(get_db)` / `Depends(get_session)` | `app.dependency_overrides[get_db] = lambda: fake_session`, and `app.dependency_overrides.clear()` in teardown |
| Uses a SQLAlchemy session directly | The session factory the module imports. If the existing tests already run against in-memory SQLite, follow that house style |
| Opens a raw `psycopg`/`sqlite3` connection in the handler | The connect function, returning a fake connection whose cursor records `execute` calls and returns rows the test sets |
| Uses the Django ORM | See §9 |

Write the fake once, in `conftest.py`, as a small in-memory store that implements **exactly** the query features the code uses (its filter operators, ordering, single-row modes) and **raises on anything else**. A fake that silently ignores a filter lets a wrong query pass. Keep a record of writes, so tests can assert on side effects:

```python
class FakeDb:
    def __init__(self):
        self.tables, self.inserts = {}, []

    def add(self, table, *rows):
        self.tables.setdefault(table, []).extend(dict(row) for row in rows)

    def select(self, table, *, filters=None, maybe_single=False):
        rows = [dict(row) for row in self.tables.get(table, []) if _matches(row, filters)]
        if maybe_single:
            return rows[0] if rows else None
        return rows

    def insert(self, table, payload):
        self.tables.setdefault(table, []).append(dict(payload))
        self.inserts.append((table, dict(payload)))
        return dict(payload)

    def inserted(self, table):
        return [row for name, row in self.inserts if name == table]


def _matches(row, filters):
    for column, condition in (filters or {}).items():
        if not condition.startswith("eq."):
            raise AssertionError(f"FakeDb does not support the filter {column}={condition}")
        if str(row.get(column)) != condition[3:]:
            return False
    return True
```

### 4. Authenticate the Real Way

Don't switch auth off. Mint credentials with the app's own code (its token function, session signer or password hash) and send them the way a client would:

```python
@pytest.fixture
def sign_in(fake_db):
    def _sign_in(**overrides):
        user = {"id": "user-1", "email": "alice@example.com", "role": "admin", **overrides}
        fake_db.add("users", user)
        return user, {"Authorization": f"Bearer {main.make_token(user)}"}
    return _sign_in
```

Overriding the auth dependency (`app.dependency_overrides[get_current_user]`) is fine in tests about business logic. But **every protected route also gets an unauthenticated test (401) and a wrong-role test (403) through the real auth path.** Then test the auth layer's allowlist from the outside:

- Call every path that the code or docs mark as public with **no** credentials, and assert it does not get 401. That includes health checks, login, OAuth callbacks, **webhooks that third parties call**, and file links meant for `<iframe>`/`<img>`.
- Every other credential the code documents (a `?token=` query parameter, an API-key header, a signed URL) must work end to end, through the middleware, not just inside the handler.

This is where ordering bugs show up: a handler that reads `?token=`, sitting behind middleware that has already rejected the request because it has no `Authorization` header.

### 5. What to Cover, Per Route

- **Success:** the status code and the body fields that matter.
- **Validation failures:** each one. FastAPI returns 422 for a bad body or query before the handler runs; checks inside the handler return whatever it raises.
- **Auth:** unauthenticated (401) and forbidden (403), per §4.
- **Missing and foreign records:** not found, and another tenant's or organisation's id where the code checks ownership.
- **Downstream failures the handler handles:** an external API returning an error, a missing file, a timeout. Assert the status the code means to return. A broad `except Exception` is where a 400 raised one level down quietly becomes a 500.
- **Side effects:** what was written to the fake DB, and which external call was made with which key arguments.
- **Webhooks:** the documented response (many must always return 200 to stop retries), and the state change they trigger.

When a route's documented or clearly intended behaviour differs from what it does, the test asserts the intended behaviour and stays failing (`generate-tests` Step 12). Clear intent includes a docstring, a comment such as "always return 200", or an `HTTPException(400, ...)` raised by a helper the route calls.

### 6. Middleware, Exception Handlers, Background Work

- **Middleware:** through the client, as in §4. Call it directly only for logic that can't be reached over HTTP.
- **Exception handlers:** trigger each one through a route, and assert the mapped status and body.
- **`BackgroundTasks`:** they run when the `TestClient` response completes, so assert their effect after the call.
- **Threads a handler starts:** replace **only the module's own** `threading` reference with one whose `Thread.start()` runs the target at once. Never patch the real `threading.Thread`, because `TestClient` runs on threads too.

```python
class SyncThread:
    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self.target, self.args, self.kwargs = target, args, kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


@pytest.fixture
def sync_threads(monkeypatch):
    monkeypatch.setattr(main, "threading", SimpleNamespace(Thread=SyncThread))
```

### 7. External Services and Heavy Libraries

- **HTTP clients and SDKs** (`requests`, `httpx`, `anthropic`, `stripe`, Google clients): patch them where the module looks them up (`main.requests.post`), and return a small fake response with only the fields the code reads.
- **`subprocess`/`ffmpeg`:** patch `main.subprocess.run` and assert on the command arguments that matter.
- **ML models and other heavy libraries:** look at *where* they are imported. If the import is inside a function (`from resemblyzer import VoiceEncoder` in the body), the module imports fine without the library. Fake it per test, installed or not, so no test downloads a model:

```python
def test_enroll_speaker_valid_audio_stores_embedding(client, fake_db, monkeypatch):
    fake_resemblyzer = types.ModuleType("resemblyzer")
    fake_resemblyzer.preprocess_wav = lambda path: [0.1, 0.2, 0.3]
    monkeypatch.setitem(sys.modules, "resemblyzer", fake_resemblyzer)
    ...
```

  Where the module keeps a loaded model in a global (`voice_encoder = None` until first use), set that global to a fake instead. A library imported at the **top** of the module and not installed is a real import failure. Prove it (`generate-tests` Step 5a) before treating it as one.

### 8. Async Code

`TestClient` drives `async def` routes for you. To test an async helper directly, use `asyncio.run(helper(...))` in the test, unless the repo already uses `pytest-asyncio` or anyio's pytest plugin. In that case follow the house style.

### 9. Flask and Django Specifics

- **Flask:** set `app.config.update(TESTING=True)` (or use the factory's test config), and use `app.test_request_context()` for helpers that need `request`/`g`. Patch the module's data-access helpers as in §3.
- **Django:** Django's ORM needs a test database, which in pytest means `pytest-django` (`@pytest.mark.django_db`). If the repo has it, follow the house style. If not, record a tooling gap. Still test what doesn't touch the ORM: views through `RequestFactory` with the queryset-producing calls patched, plus forms, serializers and plain services. Never point a test at the development database.

### Checklist

- [ ] App built without startup side effects (bare `TestClient`, factory with test config)
- [ ] Config pinned and every write path redirected to `tmp_path` in one autouse fixture; module caches reset
- [ ] Database faked at the module's own seam, by a fake that raises on unsupported queries
- [ ] Every route covered through the client: success, validation, 401/403, not-found, downstream failures, side effects
- [ ] Every documented public path and alternative credential exercised without the usual credentials
- [ ] Only the module's own `threading` reference replaced; lazily imported heavy libraries faked via `sys.modules`
- [ ] Intended-but-broken behaviour asserted and left failing, never weakened
