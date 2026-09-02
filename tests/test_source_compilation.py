"""Fail fast if a committed Python source file cannot even be parsed."""
from pathlib import Path


def test_core_python_sources_compile():
    root = Path(__file__).resolve().parents[1] / "core"
    failures: list[str] = []
    for source in root.rglob("*.py"):
        try:
            compile(source.read_text(encoding="utf-8"), str(source), "exec")
        except SyntaxError as exc:
            failures.append(f"{source}: line {exc.lineno}: {exc.msg}")
    assert not failures, "\n".join(failures)
