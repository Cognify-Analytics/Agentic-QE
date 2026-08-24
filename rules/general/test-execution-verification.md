---
title: Post-Generation Test Execution Verification
impact: HIGH
impactDescription: ensures generated tests actually pass, not just compile
tags: tests, execution, verification, pass, fail
---

## Post-Generation Test Execution Verification

After tests compile/build successfully, run them and verify they pass. Tests that compile but fail are not deliverable.

### Process

1. **Run only the generated test file/function** (not the entire test suite):

| Build System | Command |
|--------------|---------|
| Maven | `mvn test -Dtest={TestClassName} -q` |
| Gradle | `gradle test --tests "{fully.qualified.TestClassName}" -q` |
| npm/yarn | `npx jest {testFile}` or `npm test -- --testPathPattern={testFile}` |
| Python | `python -m pytest {test_file} -v` |
| Go | `go test -run {TestFuncName} ./...` |
| .NET | `dotnet test --filter "FullyQualifiedName~{TestClassName}"` |

2. **If any test fails:**
   - Read the failure output carefully
   - Identify the root cause (wrong expected value, incorrect mock/stub setup, missing fixture, wrong assumption about behavior)
   - Fix the test — do NOT change the production code
   - Re-run to verify the fix
   - Repeat (max 3 fix attempts per failing test)

3. **If a test cannot be fixed after 3 attempts:**
   - Remove the failing test
   - Add a `# TODO:` comment explaining what was intended and why it failed
   - Inform the user about the removed test

### Common Failure Causes and Fixes

**Wrong expected value:**
```python
# Failure: expected "John Doe" but was "John"
# Fix: Read the production code to understand the actual return value
assert actual_user.name == "John"  # Match actual behavior
```

**Missing mock/stub setup:**
```python
# Failure: AttributeError / returned None unexpectedly
# Fix: Only stub what's actually called in the code path under test
mock_repository.find_by_id.return_value = user  # Verify this is called
```

**Unused stub flagged by a strict mocking framework:**
```python
# Failure: a strict-mode mocking framework flags an unused stub
# Fix: remove stubs for methods not called in this specific test scenario
# Do NOT relax the framework's strict-stub checking — remove the unnecessary stub instead
```

**Unexpected None / null in test:**
```python
# Failure: AttributeError on None when calling a method on the result
# Fix: check if the mock returns None by default — add proper stubbing
mock_service.find_by_id.return_value = None  # stub explicitly before calling, if that's the scenario
```

### IMPORTANT

- Never deliver tests that fail. Passing tests are the minimum bar.
- Do NOT modify production code to make tests pass. Fix the tests instead.
- If the production code has a bug, the test should document the CURRENT behavior and add a comment noting the suspected bug.
