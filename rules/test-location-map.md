---
title: Test Location Map
impact: HIGH
impactDescription: defines where generated tests are written, per language, without ever inventing a convention
tags: tests, location, conventions, languages
---

## Test Location Map

**We never invent a test location.** Check in this order:

### 1. Does the repo already have tests?

Use that location, even if it is unusual. The repo's convention beats the language default.

### 2. No existing tests? Use the language default.

| Language | Test location |
|---|---|
| Java (Maven, Gradle) | `src/test/java/` mirroring the package path, in the same module |
| Kotlin (Maven, Gradle) | `src/test/kotlin/` mirroring the package path, in the same module |
| Python | `tests/` |
| Go | same folder as the source file, named `*_test.go` |
| JavaScript / TypeScript (Jest, Vitest) | a root `__tests__/` mirroring the source tree, files named `*.test.ts(x)` |
| C# | a sibling `<Project>.Tests/` project |
| Rust | `tests/` for integration, inline `#[cfg(test)]` for unit |

Language folders refine this for their ecosystem: `rules/lang/python/python-test-location.md`, `rules/lang/javascript/js-ts-test-location.md` (what Jest and Vitest actually collect, helpers, Next.js `pages/`), and `rules/lang/jvm/jvm-build-and-location.md` (modules, Surefire naming, test resources).

### 3. Cannot tell?

Stop and ask the user. Do not guess.
