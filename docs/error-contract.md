# Error Contract

## Base Exception
All package-specific errors inherit from:

- ZipLogStreamError

## Exception Types

### ConfigurationError
Raised for invalid configuration values.

Examples:
- invalid chunk_size
- invalid encoding
- invalid error handler
- inconsistent config values

### ZipValidationError
Raised for invalid or unreadable ZIP inputs.

Examples:
- empty path string
- non-file path
- non-ZIP payload
- archive cannot be opened as a valid ZIP

### ZipMemberNotFoundError
Raised when no archive member matches the target.

### ZipMemberAmbiguityError
Raised when multiple members match and cannot be resolved.

## Allowed Exception
- FileNotFoundError for missing archive path

## Rules
- Do not leak stdlib ZIP exceptions
- Always use package exception types for defined failure modes
- Exception types are part of the public API

## Catching Strategy

Broad catch:

```python
from zip_logstream import ZipLogStreamError

try:
    ...
except ZipLogStreamError:
    ...
```

Targeted catch:

```python
from zip_logstream import ZipValidationError, ZipMemberAmbiguityError

try:
    ...
except ZipValidationError:
    ...
except ZipMemberAmbiguityError:
    ...
```
