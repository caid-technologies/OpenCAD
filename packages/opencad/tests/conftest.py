"""Shared fixtures for the ``opencad`` core test suite.

The unit tests here run against nothing but the installed package. A handful
of integration tests additionally exercise repository artifacts that live
outside this distribution (``examples/`` scripts and the published JSON
schemas under ``docs/``). Those tests locate the repo by walking upward and
skip cleanly when this package is tested outside a monorepo checkout, so
``pytest`` inside ``packages/opencad`` always works standalone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# A directory is the repo root if it holds both of these.
_ROOT_MARKERS = ("examples", "docs")


def find_repo_root() -> Path | None:
    for candidate in Path(__file__).resolve().parents:
        if all((candidate / marker).is_dir() for marker in _ROOT_MARKERS):
            return candidate
    return None


REPO_ROOT = find_repo_root()


def require_repo_root() -> Path:
    """Return the repo root, or skip the calling test when it is absent."""
    if REPO_ROOT is None:
        pytest.skip("requires a monorepo checkout (examples/ and docs/ not found)")
    return REPO_ROOT


@pytest.fixture()
def repo_root() -> Path:
    return require_repo_root()


@pytest.fixture()
def examples_dir(repo_root: Path) -> Path:
    return repo_root / "examples"
