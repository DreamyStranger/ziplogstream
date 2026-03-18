# Claude Instructions — ziplogstream

## Overview
Maintain a production-quality Python library for bounded-memory streaming of text lines from ZIP archive members.

Priorities:
- correctness
- minimal diffs
- stable public API
- performance

## Core Rules
- Make minimal, targeted changes only
- Do not refactor unrelated code
- Do not change public API unless explicitly asked
- Preserve existing structure and naming
- Avoid new dependencies unless explicitly requested
- Prefer explicit code over abstraction
- Performance regressions are not acceptable

## Performance Rules
- Streaming must remain **bounded-memory**
- Do not introduce full-file buffering or unbounded accumulation
- Avoid unnecessary allocations or copies in hot paths
- Preserve chunked reading behavior
- Do not degrade performance for large files or long lines
- Prefer simple, predictable operations over complex abstractions

Hot paths include:
- buffered line iteration
- chunk decoding
- segment detection

Any change affecting these must preserve current performance characteristics.

## Public API
Treat these as public and stable:
- `LineStreamer`
- `LineStreamerConfig`
- `ZipMemberResolver`
- `default_zip_member_resolver`
- `ZipLogStreamError`
- `ConfigurationError`
- `ZipValidationError`
- `ZipMemberNotFoundError`
- `ZipMemberAmbiguityError`
- `__version__`

Do not remove or rename public exports without being asked.

## Error Handling Contract
- All package-specific errors must derive from `ZipLogStreamError`
- Do not leak stdlib ZIP exceptions when a package exception should be raised
- Use:
  - `ConfigurationError` for invalid config values
  - `ZipValidationError` for invalid ZIP inputs / unreadable archives
  - `ZipMemberNotFoundError` for no matching member
  - `ZipMemberAmbiguityError` for multiple matching members
- `FileNotFoundError` is allowed for a missing archive path

See `docs/error-contract.md` for details.

## Project Structure
- `src/ziplogstream/archive/` handles ZIP path validation and member resolution
- `src/ziplogstream/streaming/` handles streaming and buffered line iteration
- `src/ziplogstream/config.py` defines immutable streaming config
- `tests/unit/` covers isolated behavior
- `tests/integration/` covers ZIP-backed end-to-end behavior

See `docs/architecture.md` when needed.

## Testing Rules
- Add tests when behavior changes
- Prefer focused unit tests over broad rewrites
- Do not rewrite existing tests unless they are incorrect
- Test public behavior, not implementation trivia

See `docs/testing.md` for commands.

## Release Rules
- Version is sourced dynamically from `src/ziplogstream/version.py`
- Do not edit `pyproject.toml` for version bumps
- Releases are triggered by pushing a git tag like `v0.1.0`

See `docs/release.md` for the exact flow.

## Output Requirements
- Return only relevant code changes unless explanations are requested
- Prefer patch-ready edits
- Do not repeat large unchanged blocks