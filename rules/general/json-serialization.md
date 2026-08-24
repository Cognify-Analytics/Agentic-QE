---
title: Serialized Payloads in Tests
impact: HIGH
impactDescription: prevents test fragility and ensures explicit test data
tags: tests, json, serialization, payloads
---

## Serialized Payloads in Tests

Use explicit literal payloads (JSON, YAML, or similar) instead of the same runtime serializer under test, so tests are deterministic and clearly show expected data.

This is a specific case of the "no logic in tests" principle, applied to serialized data.

### Rules

- **DO NOT** derive an expected serialized payload by invoking the same serialization path under test (e.g. calling the app's own JSON encoder to build the "expected" string)
- You **MUST** use explicit literal payloads in stubs and assertions

**Incorrect (Python):**

```python
def test_create_user_valid_request_returns_201():
    # Using the app's own serializer - fragile, unclear expected format
    request = UserRequest("John", "john@test.com")
    request_json = json.dumps(request.__dict__)

    response = client.post("/users", data=request_json, content_type="application/json")

    assert response.status_code == 201

def test_get_user_existing_id_returns_user():
    # Serializing the response for comparison - hides expected structure
    expected_user = User("1", "John")
    service.find_by_id.return_value = expected_user

    result = controller.get_user("1")

    # Comparing two serializer outputs against each other proves nothing new
    assert json.dumps(result.__dict__) == json.dumps(expected_user.__dict__)
```

**Correct:**

```python
def test_create_user_valid_request_returns_201():
    # Explicit literal payload - clear, deterministic
    request_json = '{"name": "John", "email": "john@test.com"}'

    response = client.post("/users", data=request_json, content_type="application/json")

    assert response.status_code == 201

def test_get_user_existing_id_returns_user_json():
    # Explicit expected fields in the assertion
    service.find_by_id.return_value = User("1", "John")

    response = client.get("/users/1")

    body = response.json()
    assert response.status_code == 200
    assert body["id"] == "1"
    assert body["name"] == "John"

# For HTTP-mocking stubs
def test_fetch_data_valid_response_parses_correctly(http_mock):
    # Explicit stub response
    http_mock.get("/api/data").respond_with_json({"status": "success", "data": {"value": 42}})
    # ...
```

### Note on Web-Layer Tests

The rule applies equally whether you're testing a full request/response cycle (e.g. a route/controller test using an in-process test client) or a pure unit test that happens to produce or consume serialized data — in both cases, write the expected payload as a literal, not as the output of the same encode/decode path being tested.

### Benefits

1. **Readability** — expected data is visible directly in the test
2. **Determinism** — no dependency on serializer configuration (key order, whitespace, float formatting)
3. **Debugging** — easy to see what's being tested
4. **Maintenance** — changes to serializer settings don't break tests
