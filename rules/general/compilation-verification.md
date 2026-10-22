---
title: Post-Generation Compilation Verification
impact: HIGH
impactDescription: ensures generated tests compile/build successfully before delivery
tags: tests, compilation, verification, build, ci
---

## Post-Generation Compilation Verification

After generating test files, verify they compile/build successfully. Fix any issues before completing the task.

### Compilation Commands by Build System

Use the project's wrapper (`./mvnw`, `./gradlew`) and package manager (`pnpm exec`, `yarn`) when present.

| Build System | Command |
|--------------|---------|
| Maven | `./mvnw -q test-compile` (multi-module: add `-pl <module> -am`) |
| Gradle (Java/Kotlin) | `./gradlew testClasses -q` (multi-project: `:<project>:testClasses`) |
| TypeScript | `npx tsc --noEmit -p <tsconfig that includes the tests>`, judged only on the files you wrote |
| JavaScript | no compile step; the test run is the check |
| Python | `python -m py_compile <test_file>` |
| Go | `go build ./...` |
| Rust | `cargo check --tests` |
| .NET | `dotnet build` |
| Mix (Elixir) | `mix compile` |
| sbt (Scala) | `sbt Test/compile` |
| Swift | `swift build` |

**Only errors in files you wrote are yours.** A repo can have pre-existing type or compile errors elsewhere; filter the output to your files (`... 2>&1 | grep -F "<your test file>"`) and don't fix or block on the rest. The language folders give details: `rules/lang/javascript/test-runner-conventions.md` §2, `rules/lang/jvm/jvm-build-and-location.md` §2.

### Process

1. **Create the test file** in the correct location
2. **Run compilation** using the appropriate command
3. **If compilation fails:**
   - Read the error message
   - Fix the issue in the test file (missing imports, wrong types, wrong method or field names, syntax errors)
   - Re-run compilation
4. **Repeat until successful** (max 5 attempts)

### Missing Dependencies: Report Them, Never Add Them

**Never edit a manifest or build file** (`package.json`, `pom.xml`, `build.gradle(.kts)`, `pyproject.toml`, `requirements*.txt`) to add a test dependency. Those files aren't tests, the CI safety check fails any run that changes them, and dependencies are the developer's decision.

When a library you'd want isn't installed:

1. Use what is: the framework's built-in assertions (`assert`, JUnit `Assertions`, `node:assert`), a hand-written fake instead of a mocking library.
2. If the module genuinely can't be tested without it (React components with no DOM environment, for example), skip the module with a `skipped_reason` that names the exact package to add, so a developer can act on it.

### Common Issues and Fixes

**Missing imports:**
```python
# Error: NameError / ModuleNotFoundError
# Fix: Add the missing import
from unittest.mock import Mock, patch
import pytest
```

**Wrong module path:**
```python
# Error: ModuleNotFoundError: No module named 'src.orders'
# Fix: Verify the import path matches the package layout
from src.orders import OrderService  # must match src/orders.py's actual location
```

```ts
// Error: Cannot find module '@/lib/pricing'   (alias not mapped for tests)
// Fix: use the import style existing tests use; often a relative path
import { calculateTotal } from '../../src/lib/pricing';
```

**Invented members (the error this rule exists to catch):**
```
TS2339: Property 'totalAmount' does not exist on type 'Order'.
[ERROR] OrderServiceTest.java:[42,17] cannot find symbol: method getTotalAmount()
e: PricingTest.kt:12:5 Unresolved reference: totalAmount
# Fix: re-read the real type (generate-tests Step 6) and use the member it declares
```

**Type mismatch:**
```
# Error: type checker or static-analysis failure
# Fix: check return types and parameter types
# Wrong: assert result == "123"   # if result is an int
# Correct: assert result == 123
```

### Verification Checklist

- [ ] Test file is in correct directory
- [ ] Module/package path matches directory structure
- [ ] All imports are present and correct
- [ ] Every member used exists on the real type
- [ ] No manifest or build file was changed
- [ ] No syntax errors
- [ ] Type compatibility is correct
- [ ] Compilation/build command succeeds for the files written

### Example Workflow

```bash
# 1. Create test file
# (using Write tool)

# 2. Run compilation/build check
python -m py_compile tests/test_orders.py

# 3. If errors, fix and retry
# Error: ModuleNotFoundError: No module named 'src.orders'
# Fix: correct the import path

# 4. Verify success
python -m py_compile tests/test_orders.py
# no output = success
```

**IMPORTANT:** Never deliver tests that don't compile/build. Always verify before completing the task.
