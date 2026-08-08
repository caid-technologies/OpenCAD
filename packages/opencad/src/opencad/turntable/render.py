"""Headless software renderer for turntable previews.

A small numpy z-buffer rasterizer. Deliberately dependency-free beyond
``numpy`` (already a core dependency) so turntable export works in CI and in
plain containers — anything GPU-backed (OSMesa/EGL) would not.

Conventions match the web viewport so exported previews look like what a user
sees interactively: Z-up world and a 45° vertical FOV. Preview frames use a
neutral grayscale material over transparency so GIFs can be placed on any
background without carrying a colored rectangle with them.
"""

from __future__ import annotations

import math

import numpy as np

# Matches the viewport's `camera={{ position: [45, -55, 30], up: [0, 0, 1], fov: 45 }}`.
VIEWER_FOV_DEGREES = 45.0
VIEWER_ELEVATION_DEGREES = math.degrees(math.atan2(30.0, math.hypot(45.0, 55.0)))
VIEWER_AZIMUTH_DEGREES = math.degrees(math.atan2(-55.0, 45.0))

# The model is deliberately achromatic.
MODEL_RGB = (0xA8, 0xA8, 0xA8)

# The turntable axis is world Z, not Y — the scene is Z-up.
UP_AXIS = np.array([0.0, 0.0, 1.0])

# Light is fixed relative to the camera rather than to the world, so every
# frame of the revolution is lit identically. A world-fixed light would swing
# the model through its own shadow side halfway around the loop.
_LIGHT_VIEW_DIRECTION = np.array([-0.40, 0.55, 1.0])
_AMBIENT = 0.32
_DIFFUSE = 0.68

# Keeps the camera clear of the pole, where the view direction would become
# parallel to the up axis and the basis would collapse.
_MAX_ELEVATION_DEGREES = 89.0

# Breathing room around the bounding sphere so the silhouette never touches
# the frame edge.
_FIT_MARGIN = 1.12


class EmptyMeshError(ValueError):
    """Raised when there is no triangle to render."""


def mesh_arrays(
    vertices: list[float],
    faces: list[int],
    normals: list[float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert flat ``MeshData`` buffers into shaped float/int arrays.

    Vertex normals are used when the tessellation provides them, giving smooth
    shading on curved faces. When they are absent — or degenerate — geometric
    face normals are substituted so shading never depends on them being there.
    """
    position = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    triangle = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if position.size == 0 or triangle.size == 0:
        raise EmptyMeshError("Mesh has no triangles to render.")

    normal = np.asarray(normals, dtype=np.float64)
    if normal.size == position.size:
        normal = normal.reshape(-1, 3)
    else:
        normal = np.zeros_like(position)

    lengths = np.linalg.norm(normal, axis=1)
    missing = lengths < 1e-12
    if missing.any():
        normal[missing] = _geometric_normals(position, triangle)[missing]
        lengths = np.linalg.norm(normal, axis=1)

    normal = normal / np.where(lengths[:, None] < 1e-12, 1.0, lengths[:, None])
    return position, triangle, normal


def _geometric_normals(position: np.ndarray, triangle: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals accumulated from adjacent triangles."""
    a, b, c = (position[triangle[:, i]] for i in range(3))
    face_normal = np.cross(b - a, c - a)

    accumulated = np.zeros_like(position)
    for corner in range(3):
        np.add.at(accumulated, triangle[:, corner], face_normal)

    lengths = np.linalg.norm(accumulated, axis=1)
    fallback = np.zeros_like(accumulated)
    fallback[:, 2] = 1.0
    return np.where(lengths[:, None] < 1e-12, fallback, accumulated)


def bounding_sphere(position: np.ndarray) -> tuple[np.ndarray, float]:
    """Center and radius used to frame the model.

    The center is the bounding-box midpoint and the radius covers every vertex
    from it. Because the turntable spins about a vertical axis *through this
    center*, the sphere is rotation-invariant — framing computed from it holds
    for every frame, not just the first. Framing from the initial silhouette
    instead would clip elongated parts a quarter turn in.
    """
    center = (position.min(axis=0) + position.max(axis=0)) / 2.0
    radius = float(np.linalg.norm(position - center, axis=1).max())
    if radius < 1e-9:
        radius = 1.0
    return center, radius


def fit_distance(
    position: np.ndarray,
    center: np.ndarray,
    azimuths_degrees: np.ndarray,
    elevation_degrees: float,
    fov_degrees: float,
    aspect: float,
) -> float:
    """Smallest camera distance that keeps the model in frame for *every* azimuth.

    Solved exactly rather than by bounding sphere. For a camera at distance
    ``d`` along view direction ``dir``, a vertex at offset ``(u, v, w)`` in the
    camera basis projects inside the vertical field of view when
    ``d >= w + |v| / tan(fov/2)``, and likewise horizontally. Taking the
    maximum over all vertices and all frames gives one distance that holds for
    the whole revolution.

    A bounding sphere would also be rotation-invariant and much simpler, but it
    is badly loose for the plate- and bracket-shaped parts CAD produces: a
    80x30x4 bracket has a sphere radius set by its diagonal, so the part would
    render small in a mostly empty frame.
    """
    # Shrinking the field of view rather than scaling the distance adds an even
    # border without also flattening the perspective.
    half_vertical = math.radians(fov_degrees) / 2.0
    tan_vertical = math.tan(half_vertical) / _FIT_MARGIN
    tan_horizontal = tan_vertical * aspect

    elevation = math.radians(
        max(-_MAX_ELEVATION_DEGREES, min(_MAX_ELEVATION_DEGREES, elevation_degrees))
    )
    offset = position - center

    required = 0.0
    depth_clearance = 0.0
    for azimuth_degrees in azimuths_degrees:
        azimuth = math.radians(float(azimuth_degrees))
        direction = np.array([
            math.cos(elevation) * math.cos(azimuth),
            math.cos(elevation) * math.sin(azimuth),
            math.sin(elevation),
        ])
        right = np.cross(-direction, UP_AXIS)
        right = right / np.linalg.norm(right)
        true_up = np.cross(right, -direction)

        along_view = offset @ direction
        horizontal = np.abs(offset @ right)
        vertical = np.abs(offset @ true_up)

        needed = np.maximum(
            along_view + vertical / tan_vertical,
            along_view + horizontal / tan_horizontal,
        )
        required = max(required, float(needed.max()))
        depth_clearance = max(depth_clearance, float(along_view.max()))

    # Guard the degenerate case where the frontmost vertex sits on the view
    # axis: without clearance the camera would land on the surface and the
    # perspective divide would blow up.
    radius = float(np.linalg.norm(offset, axis=1).max())
    return max(required, depth_clearance + 0.05 * max(radius, 1e-9))


def frame_azimuths(frames: int, start_degrees: float) -> np.ndarray:
    """Evenly spaced azimuths for one full revolution.

    The final position (360°) is *not* emitted because it duplicates the first
    frame — that omission is what makes the loop close seamlessly instead of
    stalling for one frame at the wrap point.
    """
    if frames < 2:
        raise ValueError("A turntable needs at least 2 frames.")
    step = 360.0 / frames
    return np.array([start_degrees + step * index for index in range(frames)])


def _view_basis(eye: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Rotation taking world space into a camera looking down its own -Z."""
    forward = target - eye
    forward = forward / np.linalg.norm(forward)
    right = np.cross(forward, UP_AXIS)
    right = right / np.linalg.norm(right)
    true_up = np.cross(right, forward)
    return np.stack([right, true_up, -forward])


def render_frame(
    position: np.ndarray,
    triangle: np.ndarray,
    normal: np.ndarray,
    *,
    center: np.ndarray,
    distance: float,
    azimuth_degrees: float,
    elevation_degrees: float,
    width: int,
    height: int,
    fov_degrees: float = VIEWER_FOV_DEGREES,
    model_color: tuple[int, int, int] = MODEL_RGB,
    supersample: int = 2,
) -> np.ndarray:
    """Rasterize one frame as an ``(height, width, 4)`` RGBA uint8 array.

    Rendered at ``supersample``× and box-filtered down, which matters more here
    than it would for organic geometry: CAD silhouettes are dominated by long
    straight edges, and those alias badly at preview resolutions.
    """
    render_width = width * supersample
    render_height = height * supersample

    elevation = math.radians(
        max(-_MAX_ELEVATION_DEGREES, min(_MAX_ELEVATION_DEGREES, elevation_degrees))
    )
    azimuth = math.radians(azimuth_degrees)
    eye = center + distance * np.array([
        math.cos(elevation) * math.cos(azimuth),
        math.cos(elevation) * math.sin(azimuth),
        math.sin(elevation),
    ])

    basis = _view_basis(eye, center)
    view_position = (position - eye) @ basis.T
    view_normal = normal @ basis.T

    depth = -view_position[:, 2]
    focal = 1.0 / math.tan(math.radians(fov_degrees) / 2.0)
    aspect = render_width / render_height
    ndc_x = (focal / aspect) * view_position[:, 0] / depth
    ndc_y = focal * view_position[:, 1] / depth
    screen_x = (ndc_x * 0.5 + 0.5) * render_width
    screen_y = (1.0 - (ndc_y * 0.5 + 0.5)) * render_height

    # RGB is stored premultiplied while supersampling. Keeping a separate
    # coverage channel avoids baking a pale matte into antialiased edge pixels,
    # which would produce a halo when the GIF is shown on a dark background.
    color_buffer = np.zeros((render_height, render_width, 3), dtype=np.float64)
    alpha_buffer = np.zeros((render_height, render_width), dtype=np.float64)
    depth_buffer = np.full((render_height, render_width), np.inf)

    light = _LIGHT_VIEW_DIRECTION / np.linalg.norm(_LIGHT_VIEW_DIRECTION)
    base = np.asarray(model_color, dtype=np.float64)

    _rasterize(
        screen_x=screen_x,
        screen_y=screen_y,
        depth=depth,
        view_normal=view_normal,
        triangle=triangle,
        color_buffer=color_buffer,
        alpha_buffer=alpha_buffer,
        depth_buffer=depth_buffer,
        light=light,
        base=base,
    )

    color = np.clip(color_buffer, 0.0, 255.0)
    alpha = alpha_buffer
    if supersample > 1:
        color = color.reshape(height, supersample, width, supersample, 3).mean(axis=(1, 3))
        alpha = alpha.reshape(height, supersample, width, supersample).mean(axis=(1, 3))

    # Undo the premultiplication for conventional straight-alpha RGBA. Fully
    # transparent pixels stay black, though their RGB value is immaterial.
    scale = np.divide(255.0, alpha, out=np.zeros_like(alpha), where=alpha > 0.0)
    color *= scale[:, :, None]
    return np.concatenate([color, alpha[:, :, None]], axis=2).astype(np.uint8)


def _rasterize(
    *,
    screen_x: np.ndarray,
    screen_y: np.ndarray,
    depth: np.ndarray,
    view_normal: np.ndarray,
    triangle: np.ndarray,
    color_buffer: np.ndarray,
    alpha_buffer: np.ndarray,
    depth_buffer: np.ndarray,
    light: np.ndarray,
    base: np.ndarray,
) -> None:
    """Depth-buffered triangle fill over the supersampled buffers.

    Triangles are not back-face culled. Tessellated CAD solids can carry
    inconsistently oriented faces, and culling those punches holes in the
    model; the depth buffer resolves occlusion correctly either way, so
    normals are simply flipped toward the camera for two-sided shading.
    """
    height, width = depth_buffer.shape

    tri_x = screen_x[triangle]
    tri_y = screen_y[triangle]
    tri_z = depth[triangle]
    tri_n = view_normal[triangle]

    # Screen-space bounds per triangle, clipped to the viewport up front so the
    # per-triangle loop skips off-screen work without touching pixel data.
    min_x = np.maximum(np.floor(tri_x.min(axis=1)).astype(np.int64), 0)
    max_x = np.minimum(np.ceil(tri_x.max(axis=1)).astype(np.int64), width - 1)
    min_y = np.maximum(np.floor(tri_y.min(axis=1)).astype(np.int64), 0)
    max_y = np.minimum(np.ceil(tri_y.max(axis=1)).astype(np.int64), height - 1)

    x0, x1, x2 = tri_x[:, 0], tri_x[:, 1], tri_x[:, 2]
    y0, y1, y2 = tri_y[:, 0], tri_y[:, 1], tri_y[:, 2]
    areas = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)

    keep = (min_x <= max_x) & (min_y <= max_y) & (np.abs(areas) > 1e-9)
    candidates = np.nonzero(keep)[0]

    # Front-to-back. Since back faces are not culled, roughly half of a closed
    # solid's triangles are hidden; drawing nearest first lets the depth test
    # reject them before the normal interpolation and shading run.
    candidates = candidates[np.argsort(tri_z[candidates].min(axis=1), kind="stable")]

    inverse_z = 1.0 / tri_z
    nearest = tri_z.min(axis=1)

    for index in candidates:
        lo_x, hi_x = min_x[index], max_x[index]
        lo_y, hi_y = min_y[index], max_y[index]

        depth_window = depth_buffer[lo_y : hi_y + 1, lo_x : hi_x + 1]
        # Whole-triangle occlusion test. One reduction over the window is far
        # cheaper than the barycentric pass, and for a closed solid drawn
        # front-to-back it rejects most back faces outright.
        if nearest[index] >= depth_window.max():
            continue

        pixel_x = np.arange(lo_x, hi_x + 1, dtype=np.float64)[None, :] + 0.5
        pixel_y = np.arange(lo_y, hi_y + 1, dtype=np.float64)[:, None] + 0.5

        ax, bx, cx = tri_x[index]
        ay, by, cy = tri_y[index]
        area = areas[index]

        bary_a = ((bx - pixel_x) * (cy - pixel_y) - (cx - pixel_x) * (by - pixel_y)) / area
        bary_b = ((cx - pixel_x) * (ay - pixel_y) - (ax - pixel_x) * (cy - pixel_y)) / area
        bary_c = 1.0 - bary_a - bary_b

        inside = (bary_a >= 0.0) & (bary_b >= 0.0) & (bary_c >= 0.0)
        if not inside.any():
            continue

        # Perspective-correct interpolation: barycentrics are linear in screen
        # space only for reciprocal depth, so interpolate 1/z and rescale.
        inv_za, inv_zb, inv_zc = inverse_z[index]
        inverse_depth = bary_a * inv_za + bary_b * inv_zb + bary_c * inv_zc
        inside &= inverse_depth > 0.0
        if not inside.any():
            continue
        # Kept finite outside the triangle: those lanes are masked out below,
        # but an inf would still poison the shading arithmetic with NaN.
        pixel_depth = 1.0 / np.where(inside, inverse_depth, 1.0)

        visible = inside & (pixel_depth < depth_window)
        if not visible.any():
            continue

        # Everything past this point runs on the surviving pixels only. Shading
        # the whole bounding box and masking afterwards was the dominant cost;
        # bounding boxes are typically several times the triangle's own area.
        hit_depth = pixel_depth[visible]
        weight_a = bary_a[visible] * inv_za
        weight_b = bary_b[visible] * inv_zb
        weight_c = bary_c[visible] * inv_zc

        na, nb, nc = tri_n[index]
        normal_x = (weight_a * na[0] + weight_b * nb[0] + weight_c * nc[0]) * hit_depth
        normal_y = (weight_a * na[1] + weight_b * nb[1] + weight_c * nc[1]) * hit_depth
        normal_z = (weight_a * na[2] + weight_b * nb[2] + weight_c * nc[2]) * hit_depth

        # Two-sided: a normal pointing away from the eye is flipped rather than
        # dropped, so inconsistently wound faces still shade instead of going
        # black. Dividing by the length here folds in the normalization.
        length = np.sqrt(normal_x * normal_x + normal_y * normal_y + normal_z * normal_z)
        np.maximum(length, 1e-12, out=length)
        lambert = np.abs(normal_x * light[0] + normal_y * light[1] + normal_z * light[2]) / length
        intensity = _AMBIENT + _DIFFUSE * lambert

        depth_window[visible] = hit_depth
        color_window = color_buffer[lo_y : hi_y + 1, lo_x : hi_x + 1]
        color_window[visible] = intensity[:, None] * base
        alpha_window = alpha_buffer[lo_y : hi_y + 1, lo_x : hi_x + 1]
        alpha_window[visible] = 255.0
