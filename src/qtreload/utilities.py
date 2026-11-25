"""Utilities."""

from __future__ import annotations

import ast
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
    """Resolve the root for a module spec.

    Packages resolve to their directory, single-file modules resolve to the file itself and modules without a
    location on disk (built-in, frozen) resolve to None.
    """
    search_locations = spec.submodule_search_locations
    if spec.origin is not None and spec.has_location:
        origin = Path(spec.origin)
        return origin.parent if search_locations is not None else origin

    if not search_locations:
        return None

    search_paths = [Path(location) for location in search_locations]
    if len(search_paths) != 1:
        return None
    return search_paths[0]


def get_import_path(module: str) -> Path | None:
    """Get the module path, or None if the module (or one of its parent packages) cannot be found."""
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        return None
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
    """Get python and stylesheet paths for a package or a single-file module."""
    module_path = get_path_for_module(module)
    if module_path.is_file():
        return ([module_path] if module_path.suffix == ".py" else []), []
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


def path_to_module(path: str, module_path: Path, module: str | None = None) -> str:
    """Turn a file path into a module name.

    Parameters
    ----------
    path : str
        Path to the python file.
    module_path : Path
        Path returned by `get_import_path` for the watched module.
    module : str, optional
        Name of the watched module. When provided, the name is built relative to it, which is required for
        subpackages (e.g. 'email.mime') and single-file modules. When omitted, the watched module is assumed to be
        a top-level package.
    """
    candidate_path = Path(path).resolve()
    if module is not None:
        return _path_to_module_relative_to(candidate_path, module_path.resolve(), module)

    module_root = module_path.parent.resolve()

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


def _path_to_module_relative_to(path: Path, module_path: Path, module: str) -> str:
    """Build the module name of `path` relative to the watched `module` located at `module_path`."""
    if module_path.is_file():
        if path != module_path:
            raise ValueError(f"Path '{path}' does not belong to module '{module}'.")
        return module

    try:
        relative_path = path.relative_to(module_path)
    except ValueError as e:
        raise ValueError(f"Path '{path}' is not a subpath of '{module_path}'.") from e

    module_parts = list(relative_path.parts)
    if not module_parts:
        raise ValueError(f"Path '{path}' does not point to a Python module.")
    module_parts[-1] = Path(module_parts[-1]).stem
    if module_parts[-1] == "__init__":
        module_parts.pop()
    return ".".join([module, *module_parts])


def get_imported_modules(path: str | Path, module: str) -> set[str]:
    """Return the names of modules imported by the python file at `path`, whose module name is `module`.

    Relative imports are resolved, parent packages are included (`import a.b` gives 'a' and 'a.b') and names
    imported with `from x import y` are included as possible submodules ('x.y'). Files that cannot be read or
    parsed return an empty set.
    """
    path = Path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, ValueError):
        return set()

    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                try:
                    base = importlib.util.resolve_name("." * node.level + base, package)
                except (ImportError, ValueError):
                    continue
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")

    # include parent packages of every imported name
    for name in list(names):
        parts = name.split(".")
        names.update(".".join(parts[:i]) for i in range(1, len(parts)))
    return names
