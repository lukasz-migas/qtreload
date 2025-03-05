"""Utilities."""

from __future__ import annotations

import importlib.util
import sys
import typing as ty
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


def get_path_for_module(module: str) -> Path:
    """Get the path for a module."""
    module_path = get_import_path(module)
    if module_path is None:
        raise ValueError(f"Module '{module}' not found.")
    return module_path


def get_module_paths(
    module: str,
    py_pattern: tuple[str, ...] = ("**/*.py",),
    ignore_py_pattern: tuple[str, ...] = ("**/__init__.py", "**/test_*.py"),
    stylesheet_pattern: tuple[str, ...] = ("**/*.qss",),
    log_func: ty.Callable = noop,
) -> tuple[list[Path], list[Path]]:
    """Get module paths."""
    module_path = get_import_path(module)
    if module_path is None:
        raise ValueError(f"Module '{module}' not found.")
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


def get_import_path(module: str) -> Path | None:
    """Get the module path."""
    loader = importlib.util.find_spec(module)
    if loader is None:
        return None
    path = Path(loader.origin)
    return path.parent


def path_to_module(path: str, module_path: Path) -> str:
    """Turn module path into a module name."""
    module = path.split(str(module_path.parent))[1]
    if "src" in module:
        module = module.split("src")[1]
    module = module.replace("\\", ".")[:-3] if IS_WIN else module.replace("/", ".")[:-3]
    if module.startswith("."):
        module = module[1:]
    return module
