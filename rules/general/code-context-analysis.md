---
title: Code Context Analysis
impact: HIGH
impactDescription: ensures correct test data by understanding the full dependency graph
tags: tests, context, dependencies, dto, entity, analysis
---

## Code Context Analysis

Before generating tests, read all types/structures referenced by the target code. Tests that use wrong constructors, miss required fields, or create invalid objects will fail at compile/run time or produce meaningless results.

### What to Read Before Writing Tests

After reading the target function/method/class, identify and read:

1. **Direct parameter types**: Every type used as a function/method parameter
2. **Return types**: Every type returned by the function/method under test
3. **Injected dependencies**: Collaborators passed into the constructor, factory, or function (these need mocking/faking)
4. **Domain entities / DTOs / data classes**: Types created or transformed in the function body
5. **Enums / literal unions / constant sets**: Anything used in conditionals, switch/match statements, or as parameters
6. **Custom exceptions/errors**: Error types raised by the function
7. **Validators / schema constraints**: Custom validation logic, if validation is being tested

### Why This Matters

**Without reading dependencies:**
```python
# Runs but FAILS - wrong constructor args
request = OrderRequest("product-1", 5)
# Actual signature: OrderRequest(product_id: str, quantity: int, customer_id: str)
```

**With reading dependencies:**
```python
# Correct - matches the actual constructor
request = OrderRequest("product-1", 5, "customer-123")
```

### How to Read Dependencies Efficiently

1. Read the target code's imports to identify referenced types
2. Use Glob to find the source files (e.g. `**/order_request.py`, `**/OrderRequest.ts`)
3. Read each dependency to understand:
   - Constructor/initializer parameters (types and order)
   - Required fields vs. optional fields
   - Builder or factory patterns (if present — use them)
   - Factory functions (if present — prefer over raw construction)
   - Enum/union values available

### Pay Special Attention To

- **Language idioms for object construction**: structs, dataclasses, constructors, factory functions, builder patterns — whichever the language and codebase use
- **Type constraints / schema constraints**: required-field markers, type hints, JSON schema, validation decorators, or docstring contracts that indicate constraints tests should satisfy (or intentionally violate for negative tests)
- **Inheritance/composition**: If a type extends or embeds another, read the parent/embedded type too
- **Generics/type parameters**: Understand the type parameters to use correct types in tests

### Checklist

Before writing any test:
- [ ] Read all parameter types used by the target function/method
- [ ] Read all return types
- [ ] Read domain entities/data classes created or modified in the function body
- [ ] Read enum/union types used in conditionals
- [ ] Identified constructors, builders, or factory functions for test data creation
