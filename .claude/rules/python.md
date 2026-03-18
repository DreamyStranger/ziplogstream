# Python Code Rules

Applies to: src/**/*.py

## Minimal Changes
- Make minimal, targeted edits only
- Do not refactor unrelated code
- Do not expand scope beyond the request

## API Stability
- Preserve all public API
- Do not rename or remove exported symbols
- Do not change function signatures unless explicitly asked

## Performance Safety
- Preserve bounded-memory streaming behavior
- Do not introduce full-file buffering
- Avoid unnecessary allocations in hot paths
- Do not degrade performance for large inputs

## Code Style
- Prefer explicit, readable code
- Avoid unnecessary abstraction
- Follow existing patterns in the codebase
- Keep logic local and simple

## Dependencies
- Do not introduce new dependencies
- Prefer standard library solutions

## Error Handling
- Use package exception types
- Do not leak stdlib ZIP exceptions
- Preserve exception chaining when wrapping errors
- Follow docs/error-contract.md

## Scope Control
- Modify only relevant files
- Do not rewrite modules
- Do not reorganize project structure

## Typing
- Preserve type hints
- Keep type correctness
- Do not weaken typing guarantees