---
title: Technology Stack Detection
impact: MEDIUM
impactDescription: ensures tests use correct frameworks and conventions for the project
tags: tests, technology, detection, frameworks, conventions
---

## Technology Stack Detection

When writing tests, first detect the programming language and technology stack from the project.

### Build/Package File Detection

| File | Language/Framework |
|------|-------------------|
| `pom.xml` | Java or Kotlin (Maven); Kotlin if `kotlin-maven-plugin` is present |
| `build.gradle` / `build.gradle.kts` | Java or Kotlin (Gradle); Kotlin if a `kotlin("jvm")` / `org.jetbrains.kotlin` plugin is applied and sources are under `src/main/kotlin` |
| `package.json` | JavaScript/TypeScript (npm/pnpm/yarn); TypeScript if `typescript` is a dependency or a `tsconfig.json` exists |
| `pyproject.toml` / `setup.py` / `requirements.txt` | Python |
| `Cargo.toml` | Rust |
| `go.mod` | Go |
| `*.csproj` / `*.sln` | C# (.NET) |
| `Gemfile` | Ruby |
| `mix.exs` | Elixir |
| `build.sbt` | Scala |
| `composer.json` | PHP |
| `Package.swift` | Swift |

### Test File Locations by Language

| Language | Test Location |
|----------|---------------|
| Java (Maven/Gradle) | `src/test/java/<package_path>/<ClassName>Test.java` |
| Kotlin | `src/test/kotlin/<package_path>/<ClassName>Test.kt` |
| Python | `tests/test_<module_name>.py` or `<module>_test.py` |
| JavaScript/TypeScript | `__tests__/<path>/<name>.test.ts`, or co-located `<name>.test.ts` / `<name>.spec.ts` |
| Go | `<name>_test.go` (same directory as source) |
| Rust | `src/<name>.rs` with `#[cfg(test)]` module or `tests/` directory |
| C# (.NET) | `<Project>.Tests/<ClassName>Tests.cs` |
| Ruby | `spec/<name>_spec.rb` or `test/<name>_test.rb` |
| PHP | `tests/<ClassName>Test.php` |
| Elixir | `test/<name>_test.exs` |
| Scala | `src/test/scala/<package>/<ClassName>Spec.scala` |
| Swift | `Tests/<Name>Tests/<Name>Tests.swift` |

### Language-Specific Conventions

**Apply automatically based on detected stack:**

1. Use the test framework the repo already uses. If there is none, use the idiomatic one for the language
2. Follow the language's naming conventions for test files and functions/methods
3. Place test files in the standard location for that ecosystem
4. Use the language's preferred assertion style

Python, JavaScript/TypeScript, Java and Kotlin have their own rule folders under `rules/lang/`, which go further: which runner or JUnit generation to detect and how, framework-specific seams (React, Next.js, Node backends, Spring Boot), mocking and coverage. `skills/generate-tests` Step 1 lists which folder each language reads.

**Incorrect:**

```python
# Using Java-style naming and no snake_case in a Python project
def testCalculateTotal(): ...

# Placing Python tests in a Java-style location
# src/test/python/CalculatorTest.py (wrong)
```

**Correct:**

```java
// Java conventions
// Location: src/test/java/com/example/CalculatorTest.java
void calculateTotal_validInput_returnsSum() { ... }
```

```python
# Python conventions
# Location: tests/test_calculator.py
def test_calculate_total_valid_input_returns_sum():
    ...
```
