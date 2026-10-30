# Changelog

## [Unreleased]

### Changed
- Tooling: setuptools>=77, PEP 639 license metadata, PEP 735 `[dependency-groups]`
  with `uv.lock`, ruff `select = ["ALL"]`, mypy strict, pytest-cov/pytest-timeout,
  Python 3.11-3.14 classifiers and `py.typed`. CI runs on uv (`uv sync --frozen`),
  release builds with `uv build` and publishes via trusted publishing.
  `__version__` now comes from `importlib.metadata`.
