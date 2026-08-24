---
title: Post-Generation Compilation Verification
impact: HIGH
impactDescription: ensures generated tests compile/build successfully before delivery
tags: tests, compilation, verification, build, ci
---

## Post-Generation Compilation Verification

After generating test files, verify they compile/build successfully. Fix any issues before completing the task.

### Compilation Commands by Build System

| Build System | Command |
|--------------|---------|
| Maven | `mvn test-compile -q` |
| Gradle | `gradle testClasses -q` |
| npm/yarn | `npm run build` or `npx tsc --noEmit` |
| Python | `python -m py_compile <test_file>` |
| Go | `go build ./...` |
| Rust | `cargo check --tests` |
| .NET | `dotnet build` |
| Mix (Elixir) | `mix compile` |
| sbt (Scala) | `sbt Test/compile` |
| Swift | `swift build` |

### Process

1. **Create the test file** in the correct location
2. **Run compilation** using the appropriate command
3. **If compilation fails:**
   - Read the error message
   - Fix the issue (missing imports, wrong dependencies, syntax errors)
   - Add missing dependencies to the appropriate config file
   - Re-run compilation
4. **Repeat until successful** (max 5 attempts)

### Common Issues and Fixes

**Missing imports:**
```python
# Error: NameError / ModuleNotFoundError
# Fix: Add the missing import
from unittest.mock import Mock, patch
import pytest
```

**Missing dependencies (Python, requirements.txt / pyproject.toml):**
```toml
# Add to pyproject.toml [project.optional-dependencies] or requirements-dev.txt
pytest = "^8.0"
pytest-mock = "^3.14"
```

**Missing dependencies (npm, package.json):**
```json
{
  "devDependencies": {
    "jest": "^29.0.0"
  }
}
```

**Wrong module path:**
```python
# Error: ModuleNotFoundError: No module named 'src.orders'
# Fix: Verify the import path matches the package layout
from src.orders import OrderService  # must match src/orders.py's actual location
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
- [ ] All dependencies are available
- [ ] No syntax errors
- [ ] Type compatibility is correct
- [ ] Compilation/build command succeeds

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
