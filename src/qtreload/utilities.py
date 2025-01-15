"""Utilities."""

from __future__ import annotations

import pkgutil
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"


def _get_paths_for_pattern(path: Path, patterns: tuple[str, ...]) -> list[Path]:
    paths = []
    for pattern in patterns:
        paths.extend(list(path.glob(pattern)))
    # remove duplicate entries
    paths = list(set(paths))
    return paths


def get_module_paths(
    module: str,
    py_pattern: tuple[str, ...] = ("**/*.py",),
    ignore_py_pattern=("**/__init__.py", "**/test_*.py"),
    stylesheet_pattern: tuple[str, ...] = ("**/*.qss",),
) -> tuple[list[Path], list[Path]]:
    """Get module paths."""
    module_path = get_import_path(module)
    if module_path is None:
        raise ValueError(f"Module '{module}' not found.")
    # first, get all module paths
    module_paths = _get_paths_for_pattern(module_path, py_pattern)
    # second, get all 'ignored' paths
    ignore_paths = _get_paths_for_pattern(module_path, ignore_py_pattern)
    # remove ignored paths from module paths
    module_paths = [path for path in module_paths if path not in ignore_paths]
    # third, get all stylesheet paths
    stylesheet_paths = _get_paths_for_pattern(module_path, stylesheet_pattern)
    return module_paths, stylesheet_paths


def get_import_path(module: str) -> Path | None:
    """Get the module path."""
    module = pkgutil.get_loader(module)
    if module is None:
        return None
    path = Path(module.get_filename())
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
