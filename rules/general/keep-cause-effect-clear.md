---
title: Keep Cause and Effect Clear
impact: HIGH
impactDescription: ensures tests are self-contained and easy to understand
tags: tests, readability, cause-effect, self-contained
---

## Keep Cause and Effect Clear

Write tests where the effects immediately follow the causes. Avoid relying on distant setup code.

### Problem: Hidden Setup

When setup is far from the test, it's impossible to understand the test without scrolling.

**Incorrect (Python, pytest fixture used for test-specific data):**

```python
@pytest.fixture
def counter():
    c = Counter()
    c.increment("key1", 8)
    c.increment("key2", 100)
    c.increment("key1", 0)
    c.increment("key1", 1)
    return c

# ... 200 lines later ...

def test_increment_existing_key(counter):
    # Where does 9 come from? Have to scroll up to find out!
    assert counter.get("key1") == 9
```

**Correct:**

```python
def test_increment_new_key_sets_value():
    counter = Counter()

    # Cause and effect are together
    counter.increment("key2", 100)

    assert counter.get("key2") == 100

def test_increment_existing_key_adds_to_value():
    counter = Counter()

    # Clear cause-effect relationship
    counter.increment("key1", 8)
    counter.increment("key1", 1)

    assert counter.get("key1") == 9
```

### Guidelines

1. **Put setup in the test** — if it's relevant to understanding the test
2. **Use a setup/fixture hook only for infrastructure** (mocks, containers, database connections) — not for test-specific data. This applies to any framework's setup mechanism: `@BeforeEach` (JUnit), `setUp()` (unittest), `beforeEach()` (Jest/Mocha), or a pytest fixture
3. **Avoid shared mutable state** — each test should set up its own data
4. **Keep tests self-contained** — reader shouldn't need to look elsewhere

### When a Setup/Fixture Hook Is Appropriate

Use a setup hook for infrastructure, not test data:

```python
@pytest.fixture
def service():
    # OK: infrastructure setup
    mock_server = MockWebServer()
    mock_server.start()

    # OK: creating the system under test
    svc = UserService(mock_server.url("/"))
    yield svc
    mock_server.stop()

def test_get_user_existing_user_returns_user(service, mock_server):
    # Test-specific data belongs in the test
    mock_server.enqueue_response(body='{"name": "John"}')

    actual_user = service.get_user("123")

    assert actual_user.name == "John"
```

### Benefits

- Tests are **self-documenting** — you understand the test by reading it
- Tests are **independent** — changing one test doesn't break others
- Failures are **easier to debug** — all relevant context is visible
