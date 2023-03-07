import ast
from pathlib import Path

import pytest


def test_setuppy() -> None:
    """Ensure that setup.py matches pyproject deps.

    (The setup.py file is only there for github)
    """
    tomllib = pytest.importorskip("tomllib")  # only available on py3.11

    ROOT = Path(__file__).parent.parent
    set_txt = (ROOT / "setup.py").read_text(encoding="utf-8")
    deps = ast.literal_eval(set_txt.split("install_requires=")[-1].split("]")[0] + "]")

    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)

    projdeps = set(data["project"]["dependencies"])
    assert projdeps == set(deps)

    # if using the min-req optional dependency, ensure that they
    # match the regular dependencies, but with the >= replaced by ==
    min_req = data["project"]["optional-dependencies"].get("min-req")
    if min_req:
        assert {k.replace(">=", "==") for k in projdeps} == set(min_req)
