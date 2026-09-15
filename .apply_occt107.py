from pathlib import Path
import hashlib


def replace(path, old, new):
    p = Path(path)
    text = p.read_text()
    assert text.count(old) == 1, (path, text.count(old))
    p.write_text(text.replace(old, new))


replace('packages/opencad/src/opencad/kernel/core/occt_backend.py',
'''def _build_topology_map(shape: Any, shape_id: str) -> TopologyMap:
    """Build a full TopologyMap from a native OCCT shape."""
''',
'''def _build_topology_map(shape: Any, shape_id: str, *, tolerance: float = 1e-6) -> TopologyMap:
    """Build native topology, including whole-edge world-Z ``top`` tags.

    Use geometric bounds, not cached triangulations or edge enumeration. A
    midpoint/centroid alone cannot prove that an entire curved edge is at the
    top. AddOptimal without shape-tolerance inflation uses OCCT's geometric
    confusion tolerance (1e-7), which is also the minimum comparison tolerance.
    """
    tolerance = max(tolerance, 1e-7)
    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, bounds, False, False)
    top_z = None if bounds.IsVoid() else bounds.Get()[5]
''')
replace('packages/opencad/src/opencad/kernel/core/occt_backend.py',
'''        length = _edge_length(edge)
        edge_refs.append(SubshapeRef(''',
'''        length = _edge_length(edge)
        tags: list[str] = []
        # The centroid is only a cheap prefilter; the bounds check below is
        # authoritative. Ignore zero-length pole edges and vertical seams.
        if (
            top_z is not None
            and math.isfinite(top_z)
            and length > tolerance
            and not BRep_Tool.Degenerated_s(edge)
            and abs(centroid[2] - top_z) <= tolerance
        ):
            edge_bounds = Bnd_Box()
            BRepBndLib.AddOptimal_s(edge, edge_bounds, False, False)
            if not edge_bounds.IsVoid():
                _, _, zmin, _, _, zmax = edge_bounds.Get()
                if abs(zmin - top_z) <= tolerance and abs(zmax - top_z) <= tolerance:
                    tags.append("top")
        edge_refs.append(SubshapeRef(''')
replace('packages/opencad/src/opencad/kernel/core/occt_backend.py',
'''            length=length,
            tags=[],
''', '''            length=length,
            tags=tags,
''')
replace('packages/opencad/src/opencad/kernel/core/occt_backend.py',
'''        return _build_topology_map(native, shape_id)''',
'''        return _build_topology_map(native, shape_id, tolerance=self.tolerance)''')
replace('packages/opencad/src/opencad/part.py',
'''            # Analytic topology does not carry directional tags on edges yet;
            # returning a deterministic subset keeps API ergonomic.
            return [edge.id for edge in topology.edges[:4]]''',
'''            # The owning backend certifies whole-edge geometry. Consume its
            # serialized tags so remote kernels behave exactly like local ones.
            edge_ids = [edge.id for edge in topology.edges if "top" in edge.tags]
            if not edge_ids:
                raise ValueError(
                    "No geometric top edges were reported for this shape. "
                    "'top' requires non-degenerate edges lying wholly in its "
                    "highest world-Z plane. Use an OCCT-backed context or "
                    "explicit edge IDs instead."
                )
            return edge_ids''')
for kind, param in [('fillet', 'radius'), ('chamfer', 'distance')]:
    title = kind.capitalize()
    needle = f'    def {kind}(self, *, edges: list[str] | str | None = None, {param}: float, name: str = "{title}") -> Self:\n'
    replace('packages/opencad/src/opencad/part.py', needle, needle + '''        """Finish selected edges; ``top`` uses the native whole-edge world-Z tag.

        ``None``/``all`` and explicit ID lists keep their existing behavior.
        ``top`` raises ValueError when no geometric upper edge is reported,
        including analytic-only contexts. See ``docs/EDGE_SELECTION.md``.
        """
''')
replace('packages/opencad/tests/occt/test_regressions.py',
'''"""Audit regressions: draft is repaired; four other cases remain known defects.''',
'''"""Audit regressions: draft/top selection repaired; three known cases remain.''')
replace('packages/opencad/tests/occt/test_regressions.py',
'''def test_top_selector_is_geometric(request, context, backend):''',
'''def test_top_selector_is_geometric(context, backend):''')
replace('packages/opencad/tests/occt/test_regressions.py',
'''    _known_defect(request, "OCCT-002: top selector returns the first four enumerated edges")\n''', '')
replace('packages/opencad/tests/runtime/test_fluent_api.py',
'''    part = Part().extrude(sketch, depth=5).fillet(edges="top", radius=0.5)''',
'''    # This tests analytic STEP rejection, not geometric edge selection. The
    # analytic backend cannot certify a top rim; that is covered by native tests.
    part = Part().extrude(sketch, depth=5).fillet(edges="all", radius=0.5)''')
needle = '  .chamfer(*, edges=None|"all"|"top"|[id,...], distance, name=str)\n'
replace('packages/opencad-agent/src/opencad_agent/prompting.py', needle,
        needle + '    "top" requires native geometric tags: whole edges at the shape\'s maximum world Z, including hole rims; raises if none. Not a camera/workplane direction.\n')
replace('docs/OCCT_TESTING.md', 'Four other regression cases still carry strict expected-failure marks:',
'''Top-edge selection (OCCT-002, #107) is also a normal passing regression; see
[EDGE_SELECTION.md](EDGE_SELECTION.md) for world-Z semantics and native coverage.
Three other regression cases still carry strict expected-failure marks:''')
replace('docs/OCCT_TESTING.md', '| OCCT-002 (#107) | `edges="top"` selects geometrically top edges | Selects first four enumerated edges |\n', '')
replace('docs/OCCT_TESTING.md', 'makes the remaining four ordinary blockers.', 'makes the remaining three ordinary blockers.')

expected = {
    'docs/EDGE_SELECTION.md': '0137656a7dd743bf1598c6d1e37aa38fd738ee63d694dd0fb93d52dff7039a92',
    'docs/OCCT_TESTING.md': '3d0de7e56af95ca3f3fb3e654c3b8a8fa778ad0850526cbfe4a86a2c7c7ffb4f',
    'packages/opencad-agent/src/opencad_agent/prompting.py': 'e0b605db220cf32d81c8306f5a7829815bb710d935130a2da64ebbc66ad67f7d',
    'packages/opencad/src/opencad/kernel/core/occt_backend.py': '40faee944c020bafdd8db2327efb50529eeb6e05e3f87e71212a00ffe7d215b7',
    'packages/opencad/src/opencad/part.py': 'ba1d674e9177924ab15f80523a691399d39d63c4fa6ac81a18135e738eace6e5',
    'packages/opencad/tests/occt/test_regressions.py': '5832297f9e839f5e48da71e670f150e335fb1bfe8d532823a53e6b9cbe2fe7b3',
    'packages/opencad/tests/occt/test_top_edges.py': '21c56d2c08bb744ea69614059b95f92621bd1ac017138b0112b35792538c2e74',
    'packages/opencad/tests/runtime/test_edge_selection.py': '5bd5facfd1a561afecbbccb754220e715389804907b4beeda57ec037444e2c21',
    'packages/opencad/tests/runtime/test_fluent_api.py': '4de7e7700db27d5b98ac33ed291d7448b9eafb3b1f2400658e862fed0b3f4a51',
}
for path, digest in expected.items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
print('All nine published files match the locally tested implementation.')
Path('.github/workflows/occt-107-workspace.yml').unlink()
Path(__file__).unlink()
