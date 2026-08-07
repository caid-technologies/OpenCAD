"""Headless turntable animation export.

Renders a tessellated model rotating a full 360° about the vertical (Z) axis
and encodes it as an animated GIF — or MP4 on request. Runs without a browser,
a display server, or a GPU, so the CLI, the agent, and the ``create-cad-files``
skill can emit a preview alongside the STEP/STL they already produce.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from opencad.kernel.core.models import MeshData
from opencad.turntable.encode import (
    GIF,
    MP4,
    SUPPORTED_FORMATS,
    TurntableDependencyError,
    resolve_format,
    write_animation,
)
from opencad.turntable.render import (
    EmptyMeshError,
    VIEWER_AZIMUTH_DEGREES,
    VIEWER_ELEVATION_DEGREES,
    VIEWER_FOV_DEGREES,
    bounding_sphere,
    fit_distance,
    frame_azimuths,
    mesh_arrays,
    render_frame,
)

DEFAULT_FRAMES = 60
# 25 rather than 30 because GIF frame delays are whole centiseconds: 25fps is
# exactly 40ms, so the GIF and the MP4 of the same model run for the same 2.4s.
# At 30fps the GIF would have to round to a 30ms delay and play ~11% fast.
DEFAULT_FPS = 25
DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
# Same tessellation tolerance the viewport requests, so an exported preview has
# the same surface fidelity as the interactive one.
DEFAULT_DEFLECTION = 0.1
DEFAULT_SUPERSAMPLE = 2

__all__ = [
    "GIF",
    "MP4",
    "SUPPORTED_FORMATS",
    "TurntableOptions",
    "TurntableDependencyError",
    "EmptyMeshError",
    "export_turntable",
    "render_turntable_frames",
    "resolve_format",
]


@dataclass(frozen=True)
class TurntableOptions:
    """Rendering and encoding settings for a turntable export."""

    frames: int = DEFAULT_FRAMES
    fps: int = DEFAULT_FPS
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    deflection: float = DEFAULT_DEFLECTION
    elevation_degrees: float = VIEWER_ELEVATION_DEGREES
    start_azimuth_degrees: float = VIEWER_AZIMUTH_DEGREES
    supersample: int = DEFAULT_SUPERSAMPLE

    def __post_init__(self) -> None:
        if self.frames < 2:
            raise ValueError("frames must be at least 2 to form a rotation.")
        if self.fps < 1:
            raise ValueError("fps must be at least 1.")
        if self.width < 2 or self.height < 2:
            raise ValueError("width and height must be at least 2 pixels.")
        if self.deflection <= 0:
            raise ValueError("deflection must be positive.")
        if self.supersample < 1:
            raise ValueError("supersample must be at least 1.")

    def normalized(self) -> TurntableOptions:
        """Round the frame size up to even dimensions.

        H.264 with ``yuv420p`` subsampling requires even width and height. The
        size is normalized for every format rather than only for MP4 so a GIF
        and an MP4 of the same model come out pixel-identical in dimensions.
        """
        return replace(self, width=self.width + (self.width % 2), height=self.height + (self.height % 2))


def render_turntable_frames(mesh: MeshData, options: TurntableOptions | None = None) -> list[np.ndarray]:
    """Render one full revolution and return the frames as uint8 RGB arrays."""
    settings = (options or TurntableOptions()).normalized()

    position, triangle, normal = mesh_arrays(mesh.vertices, mesh.faces, mesh.normals)
    center, _ = bounding_sphere(position)
    azimuths = frame_azimuths(settings.frames, settings.start_azimuth_degrees)

    # One distance for the whole revolution: solving per frame would fit each
    # view tighter but make the model visibly breathe as it turns.
    distance = fit_distance(
        position,
        center,
        azimuths,
        elevation_degrees=settings.elevation_degrees,
        fov_degrees=VIEWER_FOV_DEGREES,
        aspect=settings.width / settings.height,
    )

    return [
        render_frame(
            position,
            triangle,
            normal,
            center=center,
            distance=distance,
            azimuth_degrees=float(azimuth),
            elevation_degrees=settings.elevation_degrees,
            width=settings.width,
            height=settings.height,
            supersample=settings.supersample,
        )
        for azimuth in azimuths
    ]


def export_turntable(
    mesh: MeshData,
    filepath: str | Path,
    *,
    fmt: str | None = None,
    options: TurntableOptions | None = None,
) -> Path:
    """Render ``mesh`` as a turntable animation and write it to ``filepath``.

    The format comes from the file extension unless ``fmt`` overrides it. The
    format is resolved *before* rendering so an unsupported extension or a
    missing MP4 encoder fails immediately rather than after the frames are done.
    """
    settings = (options or TurntableOptions()).normalized()
    resolved = resolve_format(filepath, fmt)
    if resolved == MP4:
        _require_mp4_encoder()

    frames = render_turntable_frames(mesh, settings)
    return write_animation(frames, filepath, resolved, settings.fps)


def _require_mp4_encoder() -> None:
    """Fail fast, and by name, when MP4 was asked for without its encoder.

    Falling back to GIF here would be worse than erroring: the caller asked for
    a video and would get a file they cannot use where they meant to use it.
    """
    try:
        import imageio_ffmpeg  # noqa: F401
    except ImportError as exc:
        raise TurntableDependencyError(
            "MP4 export requires imageio-ffmpeg. Install it with: uv sync --extra video "
            "(GIF export needs only --extra render)."
        ) from exc
