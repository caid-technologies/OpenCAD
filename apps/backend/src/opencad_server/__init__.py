"""HTTP transport layer for OpenCAD.

Everything in this package is FastAPI-specific. Core packages
(``opencad``, ``opencad_kernel``, ``opencad_solver``, ``opencad_tree``,
``opencad_agent``) must never import from here — the boundary is enforced
by ``tests/test_core_boundary.py``.
"""
