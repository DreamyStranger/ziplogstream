# Testing

## Install Dev Dependencies

```bash
pip install -e .[dev]
```

## Run All Tests

```bash
pytest
```

## Run With Coverage

```bash
pytest --cov=ziplogstream --cov-report=term-missing
```

## Run Single File

```bash
pytest tests/unit/archive/test_validators.py
```

## Run Specific Test

```bash
pytest tests/unit/archive/test_validators.py -k corrupt
```

## Lint

```bash
ruff check .
```

## Type Check

```bash
mypy src
```

## Package Check

```bash
python -m build
twine check dist/*
```

## Test Structure
- tests/unit/ → isolated behavior
- tests/integration/ → ZIP-backed end-to-end behavior

## CI Expectations
- lint passes
- type checking passes
- tests pass across supported Python versions
- package builds successfully
- distributions pass twine check