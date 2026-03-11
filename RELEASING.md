# Releasing OpenCAD to PyPI

OpenCAD already uses `setuptools` via `pyproject.toml`, so publishing a release is a
standard Python packaging flow.

## 1. Prepare the release

- Update `version` in `pyproject.toml`.
- Make sure `README.md` and any user-facing docs match the release.
- Run the existing test suite from the repository root:

```bash
pytest
```

## 2. Build the distribution artifacts

Install the packaging tools:

```bash
python -m pip install -U build twine
```

Build both the source distribution and wheel:

```bash
python -m build
```

This writes release artifacts to `dist/`.

## 3. Validate the artifacts locally

Check the generated metadata before uploading:

```bash
python -m twine check dist/*
```

Optional smoke test from the built wheel:

```bash
python -m pip install --force-reinstall dist/opencad-*.whl
opencad --help
```

## 4. Upload to PyPI

Create a PyPI API token and either:

- export it for the current shell, or
- store it in `~/.pypirc`.

Example using an environment variable:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-***
python -m twine upload dist/*
```

If you want a dry run against TestPyPI first:

```bash
python -m twine upload --repository testpypi dist/*
```

## 5. Tag the release

After the upload succeeds, create and push a matching Git tag:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

Replace `X.Y.Z` with the version you released.
