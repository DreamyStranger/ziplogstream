# Release Process

## Version Source
Version is defined in:

src/ziplogstream/version.py

Update __version__ before release.

## Steps

1. Update version:

```python
__version__ = "X.Y.Z"
```

2. Update CHANGELOG.md

3. Commit:

```bash
git add src/ziplogstream/version.py CHANGELOG.md
git commit -m "Release vX.Y.Z"
```

4. Push:

```bash
git push origin master
```

5. Tag:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

## Publish Trigger
Publishing only happens when a tag matching:

v*

is pushed.

## CI / Release
- ci.yml runs tests and validation
- release.yml builds and publishes

## PyPI Trusted Publishing
Must match:
- repository owner
- repository name
- workflow: release.yml
- environment: pypi

## Post Release Check

```bash
python -m venv .venv-check
. .venv-check/bin/activate
python -m pip install --upgrade pip
pip install ziplogstream
python -c "import ziplogstream; print(ziplogstream.__version__)"
```