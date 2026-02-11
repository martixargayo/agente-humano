import py_compile
from pathlib import Path


def test_negotiation_graph_compiles():
    path = Path("backend/negotiation/negotiation_graph.py")
    py_compile.compile(str(path), doraise=True)
