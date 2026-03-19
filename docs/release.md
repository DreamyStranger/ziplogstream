# Release Process

## Version Source
Version is defined in:

src/zip_logstream/version.py

Update __version__ before release.

## Steps

1. Update version:

```python
__version__ = "X.Y.Z"
```

2. Update CHANGELOG.md

3. Commit:

```bash
git add src/zip_logstream/version.py CHANGELOG.md
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
- ci.yml runs tests and packaging validation on Linux and Windows
- release.yml requires Linux and Windows checks to pass before publishing
- the publish job uploads the Ubuntu-built distributions to PyPI

## PyPI Trusted Publishing
Must match:
- repository owner
- repository name
- workflow: release.yml
- environment: pypi

## Post Release Check

macOS / Linux:

```bash
python -m venv .venv-check
. .venv-check/bin/activate
python -m pip install --upgrade pip
pip install zip-logstream
python -c "import zip_logstream; print(zip_logstream.__version__)"
```

Windows PowerShell:

```powershell
python -m venv .venv-check
.venv-check\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install zip-logstream
python -c "import zip_logstream; print(zip_logstream.__version__)"
```
