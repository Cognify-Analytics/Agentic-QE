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
| Maven | `./mvnw -q test -Dtest={TestClassName} -Dsurefire.failIfNoSpecifiedTests=false` |
| Gradle (Java/Kotlin) | `./gradlew test --tests "{fully.qualified.TestClassName}" --console=plain` |
| Jest | `npx jest {testFile}` |
| Vitest | `npx vitest run {testFile}` (never bare `vitest`, which watches) |
| node:test | `node --test {testFile}` |
| Python | `python -m pytest {test_file} -v` |
| Go | `go test -run {TestFuncName} ./...` |
| Rust | `cargo test {test_name}` |
| .NET | `dotnet test --filter "FullyQualifiedName~{TestClassName}"` |

Never run a watch mode. A runner that never exits hangs the run (see `rules/lang/javascript/test-runner-conventions.md` §2).

2. **If any test fails, first decide whose mistake it is** (generate-tests Step 12):
   - **The test was written wrongly** (wrong expected value derived without reading the code's contract, incorrect mock/stub setup, missing fixture, wrong import): fix the test, never the production code. Re-run, up to 3 fix attempts per failing test.
   - **The test is mechanically correct and asserts a documented expectation the code contradicts:** don't spend fix attempts on it, don't weaken it, don't delete it. Keep it failing and record it under `tests_flagged_as_possible_bugs`.
   - When unsure which applies, treat it as the second case.

3. **If a test-writing mistake still fails after 3 attempts:**
   - Remove the failing test
   - Record it in `tests_removed` with what was intended and why it failed (no `TODO` comment left in the file)
   - Inform the user about the removed test

### Common Failure Causes and Fixes

**Wrong expected value:**
```python
# Failure: expected "John Doe" but was "John"
# First ask where "John Doe" came from. If it was a guess, read the code's
# contract (docstring, docs, types) and fix the expectation to match it.
# If the contract really says "John Doe", the code is what's wrong: keep the
# test failing and flag it, never rewrite it to match the current output.
assert actual_user.name == "John"
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

**Language-specific signals:**
```
Mockito UnnecessaryStubbingException     → remove the unused stub (never make it lenient)
MockKException: no answer found          → stub the call the code path really makes
Jest/Vitest "Exceeded timeout of 5000 ms" → an un-resolved mock or un-advanced fake timer, not a slow test
"An update ... was not wrapped in act(...)" → await the UI change (findBy*), don't add act() by hand
Jest "Your test suite must contain at least one test" → a helper sits where Jest collects tests; move it
```

### IMPORTANT

- Never deliver tests that fail because they were written wrongly. The only failing tests left in the suite are the ones flagged as possible bugs.
- Do NOT modify production code to make tests pass. Fix the tests instead.
- If the production code appears to have a bug, do not rewrite the test to match the current behavior, and do not leave a comment in the code or the test. Keep the test asserting the documented behavior, failing, and flag it in `tests_flagged_as_possible_bugs` for `/triage-tests` to classify.
