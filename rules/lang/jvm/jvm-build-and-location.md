---
title: JVM Build Tools, Test Location and Coverage (Java and Kotlin)
impact: HIGH
impactDescription: compiles, runs, places and measures JVM tests through Maven or Gradle exactly as the build already defines them, without editing the build
tags: java, kotlin, jvm, maven, gradle, junit, jacoco, kover, surefire, test-location
---

## JVM Build Tools, Test Location and Coverage

Shared by Java (`rules/lang/java/`) and Kotlin (`rules/lang/kotlin/`). Language idioms live in those folders; Spring Boot in `frameworks/spring-boot.md`.

### 1. Read the Build Before Writing a Test

| Look at | To learn |
|---|---|
| `pom.xml` (and a parent `<modules>` list) / `build.gradle(.kts)` + `settings.gradle(.kts)` | Maven or Gradle; which modules exist |
| `mvnw` / `gradlew` at the root | **Always use the wrapper** when present (`./mvnw`, `./gradlew`). It pins the build tool version the project needs |
| Test-scoped dependencies (`<scope>test</scope>`, `testImplementation`, `gradle/libs.versions.toml`) | Which libraries exist: JUnit 4 or 5, AssertJ, Mockito, MockK, Kotest, Hamcrest |
| `spring-boot-starter-test` | Brings JUnit 5, AssertJ, Hamcrest, Mockito (with `mockito-junit-jupiter`), JSONassert and JsonPath |
| `maven-compiler-plugin` `release`, Gradle `toolchain`/`jvmTarget` | The Java language level. Don't use syntax newer than it allows (records need 16+, pattern-matching `switch` needs 21) |

**JUnit 4 or 5:**

- `junit-jupiter` (directly or via `spring-boot-starter-test` 2.2+) → JUnit 5.
- Only `junit:junit` → JUnit 4. Write JUnit 4 tests.
- Both, with `junit-vintage-engine` → write new tests in JUnit 5, unless every existing test is JUnit 4. Then match the house.
- **Gradle runs JUnit 5 only with `useJUnitPlatform()`** on the test task. If JUnit 5 is declared but the platform isn't enabled, new tests compile and then silently don't run ("0 tests"). Report that as a build problem; don't edit the build to fix it.

**Never edit the build.** `pom.xml`, `build.gradle(.kts)`, `settings.gradle(.kts)`, `gradle.properties` and `libs.versions.toml` are not test files. The CI safety check fails any run that changes them, and dependencies are the developer's call. If a library you'd want (AssertJ, Mockito, MockK) isn't on the test classpath, use what is: JUnit's own assertions, a hand-written fake. If nothing workable exists, skip the module with a `skipped_reason` naming the exact dependency to add.

### 2. Commands

| Purpose | Maven | Gradle |
|---|---|---|
| Compile tests (generate-tests Step 12, compile phase) | `./mvnw -q test-compile` | `./gradlew testClasses --console=plain -q` |
| One test class | `./mvnw -q test -Dtest=OrderServiceTest -Dsurefire.failIfNoSpecifiedTests=false` | `./gradlew test --tests 'com.acme.orders.OrderServiceTest' --console=plain` |
| One test method | `-Dtest='OrderServiceTest#createOrder_validRequest_returnsOrderId'` | `--tests 'com.acme.orders.OrderServiceTest.createOrder_validRequest_returnsOrderId'` |
| Whole suite (the inventory's `test_command`) | the coverage command in §5 | `./gradlew test --continue --console=plain` |
| Coverage (generate-tests Step 13) | §5 | §5 |

- **Multi-module Maven:** run from the root with `-pl <module> -am` (`-am` also builds the modules it depends on). Keep `-Dsurefire.failIfNoSpecifiedTests=false`, because the other modules in the reactor have no class matching `-Dtest`.
- **Multi-project Gradle:** prefix the task with the project path, `./gradlew :orders:test --tests '...'`.
- `--console=plain` keeps Gradle's output greppable for triage.
- Compile errors read like `[ERROR] .../OrderServiceTest.java:[42,17] cannot find symbol` (Maven) or `e: file:///.../PricingTest.kt:12:5 Unresolved reference` (Kotlin). Only errors in files you wrote are yours to fix.
- After a run, the structured results are in `target/surefire-reports/` (Maven) and `build/test-results/test/TEST-*.xml` (Gradle). They're more reliable for extracting failures than the console.

### 3. Which Classes Actually Run

**Maven Surefire only runs classes whose names match its includes:** `Test*`, `*Test`, `*Tests`, `*TestCase`. A class named `OrderServiceSpec` or `OrderServiceShould` compiles and never runs. Gradle runs every class in the test source set.

- Name test classes `<ClassUnderTest>Test` (the project convention). Use `*Tests` only if that's the house style.
- `*IT` classes run under Failsafe in the `integration-test` phase. They're integration tests, out of scope for v1. Don't write them, and don't "fix" existing ones.

### 4. Location

Test classes mirror the production package, in the test source set of the **same module**:

```
src/main/java/com/acme/orders/OrderService.java       → src/test/java/com/acme/orders/OrderServiceTest.java
src/main/kotlin/com/acme/pricing/DiscountPolicy.kt    → src/test/kotlin/com/acme/pricing/DiscountPolicyTest.kt
orders/src/main/java/com/acme/orders/OrderService.java → orders/src/test/java/com/acme/orders/OrderServiceTest.java
```

- **Same package as the class under test.** That's what gives access to package-private members, and why no import of the class is needed. It doesn't license testing private details (`prefer-public-apis.md`).
- **Mixed Java/Kotlin modules:** write the test in the language the module's existing tests use. With no tests, use the language of the class under test.
- **Test data builders:** `src/test/java/<base package>/testdata/` (or `src/test/kotlin/...`), unless the repo already has a home for them. Use that, or Gradle's `src/testFixtures/` if the `java-test-fixtures` plugin is applied.
- **Test resources** (JSON payloads, sample files): `src/test/resources/`, under a folder named after the test's package or subject.
- **Never add or change shared test configuration:** `src/test/resources/application*.yml|properties`, `junit-platform.properties`, `mockito-extensions/`, `META-INF/services`. These change how *every* test in the module behaves, not just yours.
- Never put a test under `src/main/`.

### 5. Coverage — Report Even When Tests Fail, Still Exit Non-Zero

Two requirements pull against each other here:

- Tests flagged as possible bugs stay in the suite, **failing on purpose** (generate-tests Step 12). The coverage report must still be written when tests fail.
- `/triage-tests` decides "green suite" from the **exit code**. Anything that makes failures exit 0 (`-Dmaven.test.failure.ignore=true`, `ignoreFailures = true`) hides every failure from triage. **Never use those.**

A plain `mvn test jacoco:report` or `gradle test jacocoTestReport` stops at the first test failure and never writes the report. Use these instead:

**Maven:** run the tests, then the report as a second invocation, and return the tests' exit code. The parentheses keep the `exit` inside a subshell, so triage's own `; echo "exit=$?"` still runs:

```bash
# JaCoCo already configured in pom.xml (jacoco-maven-plugin with prepare-agent):
( ./mvnw -fae test; status=$?; ./mvnw -q jacoco:report; exit $status )

# Not configured: call the plugin by its full coordinates; the pom is not touched
( ./mvnw -fae org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test; status=$?; \
  ./mvnw -q org.jacoco:jacoco-maven-plugin:0.8.12:report; exit $status )
```

`-fae` (fail at end) runs every module's tests even after one module fails. Without it, the first failing module hides the rest from triage.

Report: `target/site/jacoco/jacoco.xml` in each module. Prefer the JaCoCo version the build already declares. Older JaCoCo releases can't instrument newer JDKs ("Unsupported class file major version"); if you see that, use a newer one. If the pom sets Surefire's `<argLine>` without `@{argLine}`, the agent is dropped and no report appears. Record coverage as `null` with that reason.

This command is self-contained, so it is also the inventory's `test_command`.

**Gradle:** write a scratch init script into `.claude-pipeline/` (never committed, and not part of the build). It applies JaCoCo, turns on the XML report, and makes the report a *finalizer* of `test`. Finalizers run even when the task they finalize fails, and the build still fails. **Write it fresh every time you need coverage.** `.claude-pipeline/` is empty on a new checkout, which is also why the inventory's `test_command` for Gradle is the plain `./gradlew test --continue --console=plain` and never references this file. `/triage-tests` re-runs that command in later runs, where the script won't exist.

```groovy
// .claude-pipeline/jacoco.init.gradle
allprojects {
    plugins.withId('java') {
        apply plugin: 'jacoco'
        tasks.withType(JacocoReport).configureEach {
            reports { xml.required.set(true) }
        }
        tasks.named('test') { finalizedBy 'jacocoTestReport' }
    }
}
```

```bash
./gradlew test --continue --init-script .claude-pipeline/jacoco.init.gradle --console=plain
```

`--continue` plays the same role as Maven's `-fae`. Report: `build/reports/jacoco/test/jacocoTestReport.xml` in each project. The Kotlin JVM plugin applies `java`, so this covers Kotlin too. A repo already on **Kover** can use `koverXmlReport` (`build/reports/kover/report.xml`, same format) with the same `finalizedBy` pattern.

**Then parse, from the repo root**, passing every module's report so the total is weighted correctly:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/parse_coverage.py" orders/target/site/jacoco/jacoco.xml billing/target/site/jacoco/jacoco.xml
```

It reads JaCoCo XML and resolves `com/acme/orders/OrderService.java` to the real `orders/src/main/java/...` path.

### Checklist

- [ ] Wrapper used; build tool, modules and JUnit version read from the build, not assumed
- [ ] No build file or shared test config edited; missing libraries reported, not added
- [ ] Test class named `<Class>Test`, in the same package and same module, under `src/test/java` or `src/test/kotlin`
- [ ] No `*IT` classes written
- [ ] Compile and single-test commands scoped to the module (`-pl`/`:module:`)
- [ ] Coverage command writes the report when tests fail **and** keeps a non-zero exit code
- [ ] The inventory's `test_command` works on a fresh checkout (no reference to `.claude-pipeline/`)
- [ ] Every module's report passed to `parse_coverage.py` from the repo root
