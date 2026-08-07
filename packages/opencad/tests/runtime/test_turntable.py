"""Tests for headless turntable animation export.

Most cases build ``MeshData`` by hand rather than through the kernel, so the
renderer and encoders are covered even where OCCT is not installed. The few
tests that exercise the CLI end to end skip without it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from opencad.cli import main
from opencad.kernel.core.backend_factory import BackendUnavailableError
from opencad.kernel.core.models import MeshData
from opencad.turntable import (
    EmptyMeshError,
    TurntableDependencyError,
    TurntableOptions,
    export_turntable,
    render_turntable_frames,
    resolve_format,
)
from opencad.turntable.render import BACKGROUND_RGB, frame_azimuths

HAS_OCCT = importlib.util.find_spec("cadquery") is not None and importlib.util.find_spec("OCP") is not None
HAS_FFMPEG = importlib.util.find_spec("imageio_ffmpeg") is not None

requires_occt = pytest.mark.skipif(not HAS_OCCT, reason="CadQuery/OCP not installed")


def box_mesh(
    length: float,
    width: float,
    height: float,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> MeshData:
    """An axis-aligned box with per-face vertices, so normals are exact."""
    ox, oy, oz = origin
    corners = [
        (ox, oy, oz),
        (ox + length, oy, oz),
        (ox + length, oy + width, oz),
        (ox, oy + width, oz),
        (ox, oy, oz + height),
        (ox + length, oy, oz + height),
        (ox + length, oy + width, oz + height),
        (ox, oy + width, oz + height),
    ]
    quads = [
        ((0, 3, 2, 1), (0.0, 0.0, -1.0)),
        ((4, 5, 6, 7), (0.0, 0.0, 1.0)),
        ((0, 1, 5, 4), (0.0, -1.0, 0.0)),
        ((2, 3, 7, 6), (0.0, 1.0, 0.0)),
        ((1, 2, 6, 5), (1.0, 0.0, 0.0)),
        ((3, 0, 4, 7), (-1.0, 0.0, 0.0)),
    ]

    vertices: list[float] = []
    normals: list[float] = []
    faces: list[int] = []
    for quad, normal in quads:
        base = len(vertices) // 3
        for corner in quad:
            vertices.extend(corners[corner])
            normals.extend(normal)
        faces.extend([base, base + 1, base + 2, base, base + 2, base + 3])
    return MeshData(vertices=vertices, faces=faces, normals=normals)


def merge(*meshes: MeshData) -> MeshData:
    vertices: list[float] = []
    faces: list[int] = []
    normals: list[float] = []
    for mesh in meshes:
        offset = len(vertices) // 3
        vertices.extend(mesh.vertices)
        normals.extend(mesh.normals)
        faces.extend(index + offset for index in mesh.faces)
    return MeshData(vertices=vertices, faces=faces, normals=normals)


def asymmetric_mesh() -> MeshData:
    """An elongated L — no rotational symmetry, worst case for framing."""
    return merge(box_mesh(90, 18, 6), box_mesh(18, 55, 6))


def model_mask(frame: np.ndarray) -> np.ndarray:
    """Pixels that differ from the background, i.e. covered by the model."""
    difference = np.abs(frame.astype(np.int32) - np.asarray(BACKGROUND_RGB, dtype=np.int32))
    return difference.sum(axis=2) > 12


# ── Rotation geometry ────────────────────────────────────────────────


def test_azimuths_cover_one_revolution_without_repeating_the_wrap() -> None:
    azimuths = frame_azimuths(8, 0.0)

    assert len(azimuths) == 8
    assert azimuths[0] == 0.0
    # 360 itself is omitted; emitting it would stall the loop for one frame.
    assert azimuths[-1] == pytest.approx(315.0)
    assert np.allclose(np.diff(azimuths), 45.0)


def test_rotation_is_evenly_spaced_for_odd_frame_counts() -> None:
    azimuths = frame_azimuths(7, 12.0)

    assert np.allclose(np.diff(azimuths), 360.0 / 7)


def test_frame_azimuths_rejects_degenerate_counts() -> None:
    with pytest.raises(ValueError, match="at least 2 frames"):
        frame_azimuths(1, 0.0)


def test_loop_closes_seamlessly() -> None:
    """The frame after the last must be the first, pixel for pixel."""
    mesh = asymmetric_mesh()
    options = TurntableOptions(frames=6, width=96, height=72, supersample=1)

    frames = render_turntable_frames(mesh, options)
    # Rendering 7 positions over the same 6-frame revolution puts the 7th
    # exactly one full turn on from the first.
    wrapped = render_turntable_frames(
        mesh,
        TurntableOptions(
            frames=6,
            width=96,
            height=72,
            supersample=1,
            start_azimuth_degrees=TurntableOptions().start_azimuth_degrees + 360.0,
        ),
    )

    np.testing.assert_array_equal(frames[0], wrapped[0])
    assert not np.array_equal(frames[0], frames[-1])


def test_every_frame_differs_from_its_neighbour() -> None:
    frames = render_turntable_frames(
        asymmetric_mesh(), TurntableOptions(frames=8, width=96, height=72, supersample=1)
    )

    for index in range(len(frames)):
        assert not np.array_equal(frames[index], frames[(index + 1) % len(frames)])


# ── Framing ──────────────────────────────────────────────────────────


def test_model_stays_fully_in_frame_for_the_whole_revolution() -> None:
    """Framing from the first view alone would clip this part partway round."""
    frames = render_turntable_frames(
        asymmetric_mesh(), TurntableOptions(frames=16, width=160, height=120, supersample=1)
    )

    for index, frame in enumerate(frames):
        mask = model_mask(frame)
        assert mask.any(), f"frame {index} rendered nothing"
        rows, columns = np.nonzero(mask)
        assert rows.min() > 0 and rows.max() < frame.shape[0] - 1, f"frame {index} clipped vertically"
        assert columns.min() > 0 and columns.max() < frame.shape[1] - 1, f"frame {index} clipped horizontally"


def silhouette_centre(frame: np.ndarray) -> tuple[float, float]:
    rows, columns = np.nonzero(model_mask(frame))
    return (columns.min() + columns.max()) / 2, (rows.min() + rows.max()) / 2


def test_model_stays_centred_and_does_not_orbit_the_frame() -> None:
    """The camera targets the model's centre, so the silhouette cannot wander.

    A perfect pin is not the bar: under a 45° perspective the near side of a
    part projects larger than the far side, so the silhouette shifts slightly
    as it turns. That is what a real turntable does. What must not happen is
    the model swinging around the frame, which is what pointing the camera at
    the world origin instead of the model would cause.
    """
    frames = render_turntable_frames(
        asymmetric_mesh(), TurntableOptions(frames=12, width=160, height=120, supersample=1)
    )

    for index, frame in enumerate(frames):
        x, y = silhouette_centre(frame)
        assert abs(x - 80) < 0.2 * 160, f"frame {index} drifted horizontally"
        assert abs(y - 60) < 0.2 * 120, f"frame {index} drifted vertically"


def test_part_modelled_far_from_the_world_origin_is_still_framed() -> None:
    """Framing follows the geometry, not the origin, so offset parts stay visible."""
    at_origin = box_mesh(60, 20, 8)
    far_away = box_mesh(60, 20, 8, origin=(500.0, -300.0, 200.0))
    options = TurntableOptions(frames=6, width=160, height=120, supersample=1)

    near_frames = render_turntable_frames(at_origin, options)
    far_frames = render_turntable_frames(far_away, options)

    # Translating the model must not change a single pixel.
    for near, far in zip(near_frames, far_frames):
        np.testing.assert_array_equal(near, far)


@pytest.mark.parametrize("scale", [0.01, 1.0, 250.0])
def test_framing_is_scale_invariant(scale: float) -> None:
    """A part 25000x larger must fill the frame the same way."""
    mesh = box_mesh(30 * scale, 12 * scale, 5 * scale)
    options = TurntableOptions(frames=4, width=120, height=90, supersample=1)

    coverage = [model_mask(frame).mean() for frame in render_turntable_frames(mesh, options)]

    assert min(coverage) > 0.05
    assert max(coverage) < 0.95


def test_empty_mesh_is_rejected() -> None:
    with pytest.raises(EmptyMeshError):
        render_turntable_frames(MeshData())


def test_missing_normals_fall_back_to_geometry() -> None:
    """Tessellations without normals still shade rather than render flat."""
    mesh = box_mesh(20, 20, 20)
    without_normals = MeshData(vertices=mesh.vertices, faces=mesh.faces, normals=[])

    frames = render_turntable_frames(
        without_normals, TurntableOptions(frames=2, width=96, height=72, supersample=1)
    )

    shaded = frames[0][model_mask(frames[0])]
    assert len(np.unique(shaded[:, 0])) > 1, "expected more than one shading level"


# ── Format resolution ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("out.gif", "gif"), ("out.GIF", "gif"), ("out.mp4", "mp4"), ("a.b/out.MP4", "mp4")],
)
def test_format_is_inferred_from_the_extension(filename: str, expected: str) -> None:
    assert resolve_format(filename) == expected


def test_explicit_format_overrides_the_extension() -> None:
    assert resolve_format("preview.gif", "mp4") == "mp4"


def test_unknown_extension_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\.gif or \.mp4"):
        resolve_format("preview.webm")


def test_unknown_explicit_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="Use gif or mp4"):
        resolve_format("preview.gif", "webm")


# ── Options ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"frames": 1}, "at least 2"),
        ({"fps": 0}, "fps must be"),
        ({"width": 1}, "at least 2 pixels"),
        ({"deflection": 0.0}, "deflection must be positive"),
        ({"supersample": 0}, "supersample must be"),
    ],
)
def test_invalid_options_are_rejected(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        TurntableOptions(**kwargs)


def test_odd_frame_sizes_are_rounded_up_to_even() -> None:
    """H.264 yuv420p needs even dimensions; both formats share the rounding."""
    normalized = TurntableOptions(width=641, height=481).normalized()

    assert (normalized.width, normalized.height) == (642, 482)


def test_rendered_frames_use_the_normalized_size() -> None:
    frames = render_turntable_frames(
        box_mesh(10, 10, 10), TurntableOptions(frames=2, width=65, height=49, supersample=1)
    )

    assert frames[0].shape == (50, 66, 3)
    assert frames[0].dtype == np.uint8


# ── Encoding ─────────────────────────────────────────────────────────


def test_gif_export_writes_a_looping_animation(tmp_path: Path) -> None:
    from PIL import Image

    destination = tmp_path / "preview.gif"

    export_turntable(
        asymmetric_mesh(),
        destination,
        options=TurntableOptions(frames=8, fps=25, width=96, height=72, supersample=1),
    )

    with Image.open(destination) as animation:
        assert animation.format == "GIF"
        assert animation.n_frames == 8
        assert animation.size == (96, 72)
        assert animation.info["loop"] == 0
        assert animation.info["duration"] == 40


def test_default_frame_rate_round_trips_exactly_through_gif(tmp_path: Path) -> None:
    """GIF delays are whole centiseconds; the default must land on one exactly."""
    from PIL import Image

    destination = tmp_path / "preview.gif"
    # An asymmetric part, so no two frames are identical. Pillow merges
    # consecutive duplicate frames and sums their delays, which would mask the
    # per-frame duration for a rotationally symmetric shape.
    options = TurntableOptions(frames=4, width=64, height=48, supersample=1)

    export_turntable(asymmetric_mesh(), destination, options=options)

    with Image.open(destination) as animation:
        assert animation.info["duration"] == pytest.approx(1000 / options.fps)


def test_unrepresentable_frame_rate_snaps_to_the_nearest_centisecond(tmp_path: Path) -> None:
    """15fps is 66.7ms; it must round to 70ms, not truncate down to 60ms."""
    from PIL import Image

    destination = tmp_path / "preview.gif"

    export_turntable(
        asymmetric_mesh(),
        destination,
        options=TurntableOptions(frames=4, fps=15, width=64, height=48, supersample=1),
    )

    with Image.open(destination) as animation:
        assert animation.info["duration"] == 70


def test_gif_export_creates_missing_directories(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "deeper" / "preview.gif"

    export_turntable(
        box_mesh(10, 10, 10),
        destination,
        options=TurntableOptions(frames=2, width=64, height=48, supersample=1),
    )

    assert destination.exists()


@pytest.mark.skipif(not HAS_FFMPEG, reason="imageio-ffmpeg not installed")
def test_mp4_export_writes_a_playable_video(tmp_path: Path) -> None:
    destination = tmp_path / "preview.mp4"

    export_turntable(
        asymmetric_mesh(),
        destination,
        options=TurntableOptions(frames=8, fps=25, width=96, height=72, supersample=1),
    )

    assert destination.exists()
    # ftyp box in the first 12 bytes is what makes this a real MP4 container.
    assert destination.read_bytes()[4:8] == b"ftyp"


@pytest.mark.skipif(not HAS_FFMPEG, reason="imageio-ffmpeg not installed")
@pytest.mark.parametrize(
    ("filename", "fmt", "magic"),
    [
        ("preview.gif", "mp4", b"ftyp"),
        ("preview.mp4", "gif", b"GIF8"),
        ("preview.bin", "mp4", b"ftyp"),
        ("preview.bin", "gif", b"GIF8"),
    ],
)
def test_format_override_writes_the_requested_container_not_the_extension(
    tmp_path: Path, filename: str, fmt: str, magic: bytes
) -> None:
    """Both encoders pick their container from the file suffix by default.

    Pillow refuses an unknown suffix outright, and ffmpeg silently pairs the
    wrong muxer with the stream and exits without writing anything. Since
    `--turntable-format` exists precisely to point a format at an arbitrarily
    named destination, both must be told the format explicitly.
    """
    destination = tmp_path / filename

    export_turntable(
        asymmetric_mesh(),
        destination,
        fmt=fmt,
        options=TurntableOptions(frames=4, width=64, height=48, supersample=1),
    )

    payload = destination.read_bytes()
    assert payload, "encoder produced an empty file"
    assert magic in payload[:12]


def test_mp4_without_the_encoder_names_the_extra_to_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Must fail loudly — silently emitting a GIF would be worse than erroring."""
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)
    destination = tmp_path / "preview.mp4"

    with pytest.raises(TurntableDependencyError, match="--extra video"):
        export_turntable(
            box_mesh(10, 10, 10),
            destination,
            options=TurntableOptions(frames=2, width=64, height=48, supersample=1),
        )

    # Resolved before rendering, so nothing half-written is left behind.
    assert not destination.exists()


# ── CLI ──────────────────────────────────────────────────────────────


@requires_occt
def test_cli_renders_a_turntable_gif(tmp_path: Path) -> None:
    from PIL import Image

    script_path = tmp_path / "model.py"
    gif_path = tmp_path / "preview.gif"
    script_path.write_text("from opencad import Part\nPart().box(30, 12, 5)\n", encoding="utf-8")

    code = main([
        "run",
        str(script_path),
        "--turntable",
        str(gif_path),
        "--turntable-frames",
        "6",
        "--turntable-size",
        "96x72",
        "--backend",
        "occt",
    ])

    assert code == 0
    with Image.open(gif_path) as animation:
        assert animation.n_frames == 6
        assert animation.size == (96, 72)


@requires_occt
def test_cli_renders_a_turntable_alongside_a_step_export(tmp_path: Path) -> None:
    """The turntable must not disturb the existing CAD export path."""
    script_path = tmp_path / "model.py"
    step_path = tmp_path / "part.step"
    gif_path = tmp_path / "part.gif"
    script_path.write_text("from opencad import Part\nPart().box(20, 20, 8)\n", encoding="utf-8")

    code = main([
        "run",
        str(script_path),
        "--export",
        str(step_path),
        "--turntable",
        str(gif_path),
        "--turntable-frames",
        "4",
        "--turntable-size",
        "64x48",
        "--backend",
        "occt",
    ])

    assert code == 0
    assert step_path.read_text(encoding="utf-8").startswith("ISO-10303-21;")
    assert gif_path.exists()


def test_cli_rejects_a_turntable_on_the_analytic_backend(tmp_path: Path) -> None:
    script_path = tmp_path / "model.py"
    script_path.write_text("from opencad import Part\nPart().box(1, 1, 1)\n", encoding="utf-8")

    with pytest.raises(BackendUnavailableError, match="cannot tessellate"):
        main([
            "run",
            str(script_path),
            "--turntable",
            str(tmp_path / "preview.gif"),
            "--backend",
            "analytic",
        ])


def test_cli_rejects_an_unsupported_turntable_extension(tmp_path: Path) -> None:
    script_path = tmp_path / "model.py"
    script_path.write_text("from opencad import Part\nPart().box(1, 1, 1)\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"\.gif or \.mp4"):
        main(["run", str(script_path), "--turntable", str(tmp_path / "preview.webm")])


def test_cli_rejects_a_malformed_turntable_size(tmp_path: Path) -> None:
    script_path = tmp_path / "model.py"
    script_path.write_text("from opencad import Part\nPart().box(1, 1, 1)\n", encoding="utf-8")

    with pytest.raises(ValueError, match="WIDTHxHEIGHT"):
        main([
            "run",
            str(script_path),
            "--turntable",
            str(tmp_path / "preview.gif"),
            "--turntable-size",
            "640",
        ])


def test_run_without_a_turntable_is_unchanged(tmp_path: Path) -> None:
    """Nothing is rendered, and the analytic backend still works, when unused."""
    script_path = tmp_path / "model.py"
    tree_path = tmp_path / "tree.json"
    script_path.write_text("from opencad import Part\nPart().box(1, 1, 1)\n", encoding="utf-8")

    code = main(["run", str(script_path), "--tree-output", str(tree_path), "--backend", "analytic"])

    assert code == 0
    assert not list(tmp_path.glob("*.gif"))


@requires_occt
def test_runtime_context_exposes_turntable_export(tmp_path: Path) -> None:
    """The agent and skill call this rather than shelling out to the CLI."""
    from opencad import Part
    from opencad.kernel.core.backend_factory import create_backend
    from opencad.runtime import RuntimeContext, set_default_context

    context = RuntimeContext(backend=create_backend("occt", id_strategy="readable"))
    set_default_context(context)
    Part().box(25, 10, 4)

    destination = context.export_turntable(
        context.last_shape_id,
        str(tmp_path / "preview.gif"),
        options=TurntableOptions(frames=4, width=64, height=48, supersample=1),
    )

    assert destination.exists()
