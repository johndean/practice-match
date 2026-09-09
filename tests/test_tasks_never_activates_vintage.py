"""A-C7 (8) / A-C8 (2), m1: nothing under `app/tasks/` may ever call `app.census.vintage.activate`
-- flipping `active_vintage` (the table the API reads) stays operator-initiated, through
`scripts/census_load.py activate`, never a scheduled task. Enforced at the AST level, not a text
grep: `app/tasks/census.py`'s own module docstring explains and quotes this very rule in prose
("NOTHING here ever calls app.census.vintage.activate"), so a plain substring search for
"app.census.vintage" or "activate(" would false-positive on the very sentence that states it."""
from __future__ import annotations

import ast
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parent.parent / "app" / "tasks"


def _imports_vintage(tree: ast.AST) -> bool:
    """True if the module imports `app.census.vintage` in any form: `import app.census.vintage`
    or `from app.census import vintage`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "app.census.vintage" for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom):
            if node.module == "app.census.vintage":
                return True
            if node.module == "app.census" and any(alias.name == "vintage" for alias in node.names):
                return True
    return False


def _calls_activate(tree: ast.AST) -> bool:
    """True if the module calls anything named `activate(...)`, however it is reached
    (`vintage.activate(...)`, `x.activate(...)`, or a bare `activate(...)`)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "activate":
                return True
            if isinstance(func, ast.Name) and func.id == "activate":
                return True
    return False


def test_no_module_under_app_tasks_imports_or_calls_vintage_activate():
    py_files = sorted(TASKS_DIR.glob("*.py"))
    assert py_files, "app/tasks/ should contain at least celery_app.py and census.py"
    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not _imports_vintage(tree), f"{path.name} imports app.census.vintage"
        assert not _calls_activate(tree), f"{path.name} calls something named activate(...)"


def test_the_scan_actually_detects_a_violation():
    """Proves the two helpers above are not vacuously true -- without this, a scan that always
    returned `False` would pass the real-files test above for the wrong reason."""
    bad_import_stmt = ast.parse("import app.census.vintage\n")
    bad_import_from = ast.parse("from app.census import vintage\n")
    bad_import_from_activate = ast.parse("from app.census.vintage import activate\n")
    bad_call_attr = ast.parse("from app.census import vintage as v\nv.activate(conn, 'acs5', '2023', 'john')\n")
    bad_call_name = ast.parse("activate(conn, 'acs5', '2023', 'john')\n")
    clean = ast.parse("x = 1\ndef f():\n    return x\n")

    assert _imports_vintage(bad_import_stmt) is True
    assert _imports_vintage(bad_import_from) is True
    assert _imports_vintage(bad_import_from_activate) is True
    assert _imports_vintage(clean) is False
    assert _calls_activate(bad_call_attr) is True
    assert _calls_activate(bad_call_name) is True
    assert _calls_activate(clean) is False
