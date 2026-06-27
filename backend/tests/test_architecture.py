import ast
import importlib.util
from pathlib import Path

FORBIDDEN_IMPORTS = {"app.api", "app.db", "app.core.config", "app.services"}
PROCESSING_MODULES = [
    "app.processing.preprocessor",
    "app.processing.vectorizer",
    "app.processing.mesh_builder",
    "app.processing.navigation",
]


def get_imports(module_name: str) -> set:
    spec = importlib.util.find_spec(module_name)
    source = Path(spec.origin).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def test_preprocessor_has_no_forbidden_imports():
    imports = get_imports("app.processing.preprocessor")
    violations = {i for i in imports if any(i.startswith(f) for f in FORBIDDEN_IMPORTS)}
    assert not violations, f"preprocessor imports forbidden: {violations}"


def test_vectorizer_has_no_forbidden_imports():
    imports = get_imports("app.processing.vectorizer")
    violations = {i for i in imports if any(i.startswith(f) for f in FORBIDDEN_IMPORTS)}
    assert not violations, f"vectorizer imports forbidden: {violations}"


def test_mesh_builder_has_no_forbidden_imports():
    imports = get_imports("app.processing.mesh_builder")
    violations = {i for i in imports if any(i.startswith(f) for f in FORBIDDEN_IMPORTS)}
    assert not violations, f"mesh_builder imports forbidden: {violations}"


def test_navigation_has_no_forbidden_imports():
    imports = get_imports("app.processing.navigation")
    violations = {i for i in imports if any(i.startswith(f) for f in FORBIDDEN_IMPORTS)}
    assert not violations, f"navigation imports forbidden: {violations}"
