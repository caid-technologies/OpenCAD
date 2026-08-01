"""HTTP transport layer for OpenCAD.

Everything in this package is FastAPI-specific. Core packages
(``opencad``, ``opencad.kernel``, ``opencad.solver``, ``opencad.tree``,
``opencad_agent``) must never import from here — the boundary is enforced
by ``tests/test_core_boundary.py``.
"""
