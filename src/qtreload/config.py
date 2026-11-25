"""Configuration from pyproject.toml and environment variables."""

from __future__ import annotations

import os
import sys
import typing as ty
from dataclasses import dataclass, fields
from pathlib import Path

from qtreload.reloader import PY_IGNORE_PATTERN, PY_PATTERN, RELOAD_DELAY_MS, STYLESHEET_PATTERN

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

__all__ = ["ENV_VARIABLES", "ReloadConfig", "find_pyproject", "load_config"]

# environment variable for each configuration field - lists are comma separated
ENV_VARIABLES = {
    "modules": "QTRELOAD_HOT_RELOAD_MODULES",
    "py_pattern": "QTRELOAD_PY_PATTERN",
    "ignore_py_pattern": "QTRELOAD_IGNORE_PY_PATTERN",
    "stylesheet_pattern": "QTRELOAD_STYLESHEET_PATTERN",
    "delay_ms": "QTRELOAD_DELAY_MS",
    "editor": "QTRELOAD_EDITOR",
}


@dataclass(frozen=True)
class ReloadConfig:
    """Settings of a `HotReloader`.

    Attributes
    ----------
    modules : tuple[str, ...]
        Names of the modules to watch.
    py_pattern : tuple[str, ...]
        Glob patterns of python files to watch.
    ignore_py_pattern : tuple[str, ...]
        Glob patterns of python files to skip.
    stylesheet_pattern : tuple[str, ...]
        Glob patterns of stylesheet files to watch.
    delay_ms : int
        Changes are reloaded once no new change was seen for this many milliseconds.
    editor : str, optional
        Command used to open source files, with `{path}` and `{line}` placeholders, e.g.
        "pycharm --line {line} {path}" or "code -g {path}:{line}".
    """

    modules: tuple[str, ...] = ()
    py_pattern: tuple[str, ...] = PY_PATTERN
    ignore_py_pattern: tuple[str, ...] = PY_IGNORE_PATTERN
    stylesheet_pattern: tuple[str, ...] = STYLESHEET_PATTERN
    delay_ms: int = RELOAD_DELAY_MS
    editor: str | None = None

    def reloader_kwargs(self) -> dict[str, ty.Any]:
        """Keyword arguments of `HotReloader` (and `QtReloadWidget`) other than the modules."""
        return {
            "py_pattern": self.py_pattern,
            "ignore_py_pattern": self.ignore_py_pattern,
            "stylesheet_pattern": self.stylesheet_pattern,
            "delay_ms": self.delay_ms,
        }


def find_pyproject(start: str | Path | None = None) -> Path | None:
    """Return the nearest pyproject.toml with a [tool.qtreload] table, searching up from `start` (default: cwd)."""
    directory = Path(start or Path.cwd()).resolve()
    for candidate_dir in (directory, *directory.parents):
        candidate = candidate_dir / "pyproject.toml"
        if candidate.is_file() and "qtreload" in _read_pyproject(candidate).get("tool", {}):
            return candidate
    return None


def load_config(
    start: str | Path | None = None,
    environ: ty.Mapping[str, str] | None = None,
) -> ReloadConfig:
    """Load the configuration from defaults, [tool.qtreload] in pyproject.toml and environment variables.

    Later sources win: values from the nearest pyproject.toml with a [tool.qtreload] table (searching up from
    `start`, default: the current directory) replace the defaults, and environment variables (see `ENV_VARIABLES`)
    replace both. An environment variable that is set but empty means an empty list.

    Example pyproject.toml::

        [tool.qtreload]
        modules = ["myapp", "myplugin"]
        ignore_py_pattern = ["**/test_*.py"]
        delay_ms = 300

    Raises
    ------
    ValueError
        If the pyproject table or an environment variable contains an unknown key or a value of the wrong type.
    """
    values: dict[str, ty.Any] = {}
    pyproject = find_pyproject(start)
    if pyproject is not None:
        values.update(_parse_table(_read_pyproject(pyproject)["tool"]["qtreload"], pyproject))
    values.update(_parse_environ(os.environ if environ is None else environ))
    return ReloadConfig(**values)


def _read_pyproject(path: Path) -> dict[str, ty.Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _parse_table(table: ty.Any, path: Path) -> dict[str, ty.Any]:
    """Validate the [tool.qtreload] table."""
    if not isinstance(table, dict):
        raise ValueError(f"[tool.qtreload] in '{path}' must be a table.")  # - all config errors are ValueError
    known = {field.name for field in fields(ReloadConfig)}
    values: dict[str, ty.Any] = {}
    for key, value in table.items():
        if key not in known:
            raise ValueError(
                f"Unknown key '{key}' in [tool.qtreload] of '{path}'. Known keys: {', '.join(sorted(known))}."
            )
        if key == "delay_ms":
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"'delay_ms' in [tool.qtreload] of '{path}' must be a non-negative integer.")
            values[key] = value
        elif key == "editor":
            if not isinstance(value, str):
                raise ValueError(f"'editor' in [tool.qtreload] of '{path}' must be a string.")
            values[key] = value or None
        else:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"'{key}' in [tool.qtreload] of '{path}' must be a list of strings.")
            values[key] = _unique(value)
    return values


def _parse_environ(environ: ty.Mapping[str, str]) -> dict[str, ty.Any]:
    """Read the configuration from environment variables."""
    values: dict[str, ty.Any] = {}
    for key, variable in ENV_VARIABLES.items():
        if variable not in environ:
            continue
        raw = environ[variable]
        if key == "delay_ms":
            try:
                values[key] = int(raw)
            except ValueError as e:
                raise ValueError(f"{variable} must be a non-negative integer, got '{raw}'.") from e
            if values[key] < 0:
                raise ValueError(f"{variable} must be a non-negative integer, got '{raw}'.")
        elif key == "editor":
            values[key] = raw.strip() or None
        else:
            values[key] = _unique(raw.split(","))
    return values


def _unique(items: ty.Iterable[str]) -> tuple[str, ...]:
    """Strip items, drop empty ones and duplicates, keep the order."""
    return tuple(dict.fromkeys(item.strip() for item in items if item.strip()))
