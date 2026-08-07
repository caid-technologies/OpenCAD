"""Animation encoders for turntable previews.

GIF is the primary format and stays on a pure-Python path (Pillow) so the
common case needs no system-level ffmpeg. MP4 is opt-in and pulls a bundled
ffmpeg via ``imageio-ffmpeg``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

GIF = "gif"
MP4 = "mp4"
SUPPORTED_FORMATS = (GIF, MP4)

_EXTENSIONS = {".gif": GIF, ".mp4": MP4}

# Frames sampled to build the shared GIF palette. One palette for the whole
# animation keeps colors from shifting frame to frame; sampling around the
# revolution rather than trusting frame 0 catches surfaces that only come into
# view partway through.
_PALETTE_SAMPLES = 8


class TurntableDependencyError(RuntimeError):
    """Raised when the encoder for the requested format is not installed."""


def resolve_format(filepath: str | Path, explicit: str | None = None) -> str:
    """Pick the output format, preferring an explicit override over the suffix."""
    if explicit is not None:
        fmt = explicit.lower()
        if fmt not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported turntable format '{explicit}'. Use gif or mp4.")
        return fmt

    suffix = Path(filepath).suffix.lower()
    fmt = _EXTENSIONS.get(suffix)
    if fmt is None:
        raise ValueError(
            f"Cannot infer turntable format from '{Path(filepath).name}'. "
            "Use a .gif or .mp4 destination, or pass an explicit format."
        )
    return fmt


def write_animation(frames: list[np.ndarray], filepath: str | Path, fmt: str, fps: int) -> Path:
    """Encode ``frames`` to ``filepath`` in ``fmt``."""
    if not frames:
        raise ValueError("No frames to encode.")
    if fps < 1:
        raise ValueError("fps must be at least 1.")

    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == GIF:
        _write_gif(frames, path, fps)
    elif fmt == MP4:
        _write_mp4(frames, path, fps)
    else:
        raise ValueError(f"Unsupported turntable format '{fmt}'. Use gif or mp4.")
    return path


def _write_gif(frames: list[np.ndarray], path: Path, fps: int) -> None:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - exercised only without Pillow
        raise TurntableDependencyError(
            "GIF export requires Pillow. Install it with: uv sync --extra render"
        ) from exc

    images = [Image.fromarray(frame, mode="RGB") for frame in frames]

    stride = max(1, len(frames) // _PALETTE_SAMPLES)
    montage = np.concatenate(frames[::stride][:_PALETTE_SAMPLES], axis=0)
    palette = Image.fromarray(montage, mode="RGB").quantize(
        colors=256, method=Image.Quantize.MEDIANCUT
    )

    # Dithering is deliberately off. Shaded CAD surfaces are near-monochrome, so
    # a 256-entry adaptive palette resolves them without banding, while per-frame
    # dither noise would shimmer across the loop and inflate the file.
    quantized = [image.quantize(palette=palette, dither=Image.Dither.NONE) for image in images]

    # GIF stores frame delay in centiseconds, so the delay is rounded to the
    # nearest 10ms here rather than left for Pillow to truncate — truncation
    # turns a requested 15fps into 16.7fps. Exactly representable rates (25,
    # 20, 10 ...) round-trip unchanged; others land on the closest available.
    # Viewers also clamp very short delays, so 20ms is the floor.
    duration_ms = max(20, round(1000 / fps / 10) * 10)
    quantized[0].save(
        path,
        # Stated explicitly rather than inferred from the suffix: the caller has
        # already resolved the format, and `--turntable-format gif` is allowed to
        # point at a destination named anything. Left to Pillow, `out.mp4` would
        # raise "unknown file extension" instead of writing a GIF.
        format="GIF",
        save_all=True,
        append_images=quantized[1:],
        duration=duration_ms,
        loop=0,
        optimize=False,
        disposal=1,
    )


def _write_mp4(frames: list[np.ndarray], path: Path, fps: int) -> None:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise TurntableDependencyError(
            "MP4 export requires imageio-ffmpeg. Install it with: uv sync --extra video "
            "(GIF export needs only --extra render)."
        ) from exc

    height, width = frames[0].shape[:2]
    writer = imageio_ffmpeg.write_frames(
        str(path),
        (width, height),
        pix_fmt_in="rgb24",
        # yuv420p + even dimensions is what browsers and QuickTime expect;
        # macro_block_size=1 stops ffmpeg from silently resizing to suit itself.
        pix_fmt_out="yuv420p",
        macro_block_size=1,
        fps=fps,
        quality=7,
        # Force the container. ffmpeg otherwise picks its muxer from the output
        # suffix, so `--turntable-format mp4` aimed at `preview.gif` would pair
        # the GIF muxer with an h264 stream, and ffmpeg would exit before
        # reading a frame — leaving an empty file behind with nothing raised.
        output_params=["-f", "mp4"],
    )
    writer.send(None)
    try:
        for frame in frames:
            writer.send(np.ascontiguousarray(frame).tobytes())
    finally:
        writer.close()

    # imageio-ffmpeg never inspects ffmpeg's exit status, so a muxer or codec
    # failure surfaces only as a missing or empty file. Check the post-condition
    # rather than trust the encoder to have raised.
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(
            f"MP4 encoding produced no output at {path}. "
            "ffmpeg exited without writing a stream."
        )
