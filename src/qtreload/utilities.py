"""Utilities."""

from __future__ import annotations

import importlib.util
import sys
import typing as ty
from importlib.machinery import ModuleSpec
from pathlib import Path

IS_WIN = sys.platform == "win32"


def noop(msg: str) -> None:
    """No operation."""
    pass


def _get_paths_for_pattern(path: Path, patterns: tuple[str, ...], log_func: ty.Callable = noop) -> list[Path]:
    paths = []
    for pattern in patterns:
        try:
            files = list(path.glob(pattern))
            paths.extend(files)
        except ValueError:
            log_func(f"Pattern '{pattern}' is not valid.")

    # remove duplicate entries
    paths = list(set(paths))
    return paths


def _resolve_spec_root(spec: ModuleSpec) -> Path | None:
    """Resolve the root directory for a module spec."""
    if spec.origin is not None:
        return Path(spec.origin).parent

    search_locations = spec.submodule_search_locations
    if not search_locations:
        return None

    search_paths = [Path(location) for location in search_locations]
    if len(search_paths) != 1:
        return None
    return search_paths[0]


def get_import_path(module: str) -> Path | None:
    """Get the module path."""
    try:
        spec = importlib.util.find_spec(module)
    except ValueError as e:
        raise ValueError(f"Module '{module}' not found.") from e
    if spec is None:
        return None
    return _resolve_spec_root(spec)


def get_path_for_module(module: str) -> Path:
    """Get the path for a module."""
    module_path = get_import_path(module)
    if module_path is None:
        raise ValueError(f"Module '{module}' not found.")
    return module_path.resolve()


def get_module_paths(
    module: str,
    py_pattern: tuple[str, ...] = ("**/*.py",),
    ignore_py_pattern: tuple[str, ...] = ("**/__init__.py", "**/test_*.py"),
    stylesheet_pattern: tuple[str, ...] = ("**/*.qss",),
    log_func: ty.Callable = noop,
) -> tuple[list[Path], list[Path]]:
    """Get module paths."""
    module_path = get_path_for_module(module)
    module_paths = get_py_module_paths(module_path, py_pattern, ignore_py_pattern, log_func)
    stylesheet_paths = get_stylesheet_paths(module_path, stylesheet_pattern, log_func)
    return module_paths, stylesheet_paths


def get_py_module_paths(
    module_path: Path,
    py_pattern: tuple[str, ...] = ("**/*.py",),
    ignore_py_pattern: tuple[str, ...] = ("**/__init__.py", "**/test_*.py"),
    log_func: ty.Callable = noop,
) -> list[Path]:
    """Get module for python paths."""
    # first, get all module paths
    module_paths = _get_paths_for_pattern(module_path, py_pattern)
    # second, get all 'ignored' paths
    ignore_paths = _get_paths_for_pattern(module_path, ignore_py_pattern, log_func)
    # remove ignored paths from module paths
    module_paths = [path for path in module_paths if path not in ignore_paths]
    return module_paths


def get_stylesheet_paths(
    module_path: Path, stylesheet_pattern: tuple[str, ...] = ("**/*.qss",), log_func: ty.Callable = noop
) -> list[Path]:
    """Get module paths."""
    # third, get all stylesheet paths
    stylesheet_paths = _get_paths_for_pattern(module_path, stylesheet_pattern, log_func)
    return stylesheet_paths


def path_to_module(path: str, module_path: Path) -> str:
    """Turn a module path into a module name."""
    module_root = module_path.parent.resolve()
    candidate_path = Path(path).resolve()

    try:
        relative_path = candidate_path.relative_to(module_root)
    except ValueError as e:
        raise ValueError(f"Path '{path}' is not a subpath of '{module_path}'.") from e

    module_parts = list(relative_path.parts)
    if module_parts and module_parts[0] == "src":
        module_parts = module_parts[1:]
    if not module_parts:
        raise ValueError(f"Path '{path}' does not point to a Python module.")

    module_parts[-1] = Path(module_parts[-1]).stem
    return ".".join(module_parts)
