"""Utilities."""
import pkgutil
import sys
import typing as ty
from pathlib import Path

IS_WIN = sys.platform == "win32"


def get_import_path(module: str) -> ty.Optional[Path]:
    """Get module path."""
    module = pkgutil.get_loader(module)
    if module is None:
        return None
    path = Path(module.get_filename())
    return path.parent


def path_to_module(path: str, module_path: Path) -> str:
    """Turn path into module name."""
    module = path.split(str(module_path.parent))[1]
    if "src" in module:
        module = module.split("src")[1]
    module = module.replace("\\", ".")[:-3] if IS_WIN else module.replace("/", ".")[:-3]
    if module.startswith("."):
        module = module[1:]
    return module
