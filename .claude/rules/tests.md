# Test Rules

Applies to: tests/**/*.py

## Behavior Focus
- Test public behavior, not implementation details
- Validate guarantees, not internals

## Minimal Tests
- Add tests only for changed behavior
- Avoid redundant or overlapping tests

## Stability
- Do not rewrite existing tests unless incorrect
- Preserve test structure and naming conventions

## Style
- Prefer small, explicit test cases
- Use pytest idioms consistently
- Keep assertions clear and direct

## Error Testing
- Assert specific exception types from the public API
- Follow docs/error-contract.md for expected errors

## Scope
- Do not introduce broad test refactors
- Keep changes limited to relevant areas