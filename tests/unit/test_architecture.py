"""Import-graph guards: no runtime import cycles, and ``shared`` stays below the feature catalogs."""

import ast
import pathlib

import pytest

APP_ROOT = pathlib.Path(__file__).resolve().parents[2] / "app"

# Edges from ``app.features.shared`` into a feature package that are allowed (everything else is forbidden).
ALLOWED_SHARED_TARGETS = {"items"}


def _module_name(path: pathlib.Path) -> str:
    parts = list(path.relative_to(APP_ROOT.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _runtime_imports(tree: ast.Module) -> set[str]:
    """Every ``app.*`` module imported outside ``if TYPE_CHECKING`` blocks."""

    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            skipped.update(id(child) for child in ast.walk(node))

    found: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)

    return {name for name in found if name.startswith("app.")}


@pytest.fixture(scope="module")
def graph() -> dict[str, set[str]]:
    modules = {_module_name(path): path for path in APP_ROOT.rglob("*.py")}

    def resolve(name: str) -> str | None:
        parts = name.split(".")
        while parts:
            candidate = ".".join(parts)
            if candidate in modules:
                return candidate
            parts.pop()
        return None

    edges: dict[str, set[str]] = {}
    for module, path in modules.items():
        targets = {resolve(name) for name in _runtime_imports(ast.parse(path.read_text(encoding="utf8")))}
        edges[module] = {target for target in targets if target and target != module}

    return edges


def _cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one module (Tarjan)."""

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        index[node] = low[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        for neighbour in edges.get(node, ()):
            if neighbour not in index:
                visit(neighbour)
                low[node] = min(low[node], low[neighbour])
            elif neighbour in on_stack:
                low[node] = min(low[node], index[neighbour])
        if low[node] == index[node]:
            component = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for module in list(edges):
        if module not in index:
            visit(module)

    return components


@pytest.mark.unit
class TestImportGraph:
    def test_there_are_no_runtime_import_cycles(self, graph):
        assert _cycles(graph) == []

    def test_shared_only_depends_on_allowed_feature_packages(self, graph):
        offenders = []
        for module, targets in graph.items():
            if not module.startswith("app.features.shared"):
                continue
            for target in targets:
                parts = target.split(".")
                if parts[:2] == ["app", "features"] and len(parts) > 2 and parts[2] != "shared":
                    if parts[2] not in ALLOWED_SHARED_TARGETS:
                        offenders.append((module, target))

        assert offenders == []
