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
| Java / Kotlin (Maven, Gradle) | `src/test/java/` mirroring the package path |
| Python | `tests/` |
| Go | same folder as the source file, named `*_test.go` |
| JavaScript / TypeScript (Jest) | `__tests__/` or alongside as `*.test.ts` |
| C# | a sibling `<Project>.Tests/` project |
| Rust | `tests/` for integration, inline `#[cfg(test)]` for unit |

### 3. Cannot tell?

Stop and ask the user. Do not guess.
