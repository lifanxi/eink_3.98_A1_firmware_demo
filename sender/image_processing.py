"""Image preparation happens on the Mac; the ESP32 receives only packed pixels."""
from array import array
from pathlib import Path
from PIL import Image, ImageOps

WIDTH, HEIGHT = 768, 552
FRAME_BYTES = WIDTH * HEIGHT // 4
# Match the original project's e-ink palette. RGB values describe the preview;
# transmitted pixels contain only the four palette indices.
PALETTE = ((0, 0, 0), (255, 255, 255), (232, 176, 0), (200, 0, 0))
KERNEL = ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2))


def fit_image(image, width=WIDTH, height=HEIGHT):
    """Normalize EXIF, optionally turn clockwise once, then contain on white."""
    src = ImageOps.exif_transpose(image).convert('RGBA')
    scale = min(width / src.width, height / src.height)
    rotated_scale = min(width / src.height, height / src.width)
    # Both orientations have the same source area, so a larger fit scale
    # means more screen coverage. Keep the original orientation on a tie.
    if rotated_scale > scale:
        src = src.transpose(Image.Transpose.ROTATE_270)  # Exactly 90° clockwise.
        scale = rotated_scale
    size = (max(1, min(width, round(src.width * scale))),
            max(1, min(height, round(src.height * scale))))
    resized = src.resize(size, Image.Resampling.LANCZOS)
    left, top = (width - size[0]) // 2, (height - size[1]) // 2
    canvas = Image.new('RGBA', (width, height), (255, 255, 255, 255))
    canvas.alpha_composite(resized, (left, top))
    return canvas.convert('RGB'), (left, top, left + size[0], top + size[1])


def atkinson(rgb, bounds=None):
    """Diffuse 1/8 of RGB quantization error to each of six Atkinson neighbors."""
    rgb = rgb.convert('RGB')
    width, height = rgb.size
    left, top, right, bottom = bounds or (0, 0, width, height)
    data = array('f', map(float, rgb.tobytes()))
    indices = bytearray([1]) * (width * height)
    for y in range(top, bottom):
        for x in range(left, right):
            pos = (y * width + x) * 3
            old = (data[pos], data[pos + 1], data[pos + 2])
            best, best_dist = 0, float('inf')
            for index, color in enumerate(PALETTE):
                distance = sum((old[channel] - color[channel]) ** 2 for channel in range(3))
                if distance < best_dist:
                    best, best_dist = index, distance
            indices[y * width + x] = best
            error = tuple((old[channel] - PALETTE[best][channel]) / 8 for channel in range(3))
            for dx, dy in KERNEL:
                nx, ny = x + dx, y + dy
                # Padding stays exactly white; don't diffuse error into it.
                if left <= nx < right and top <= ny < bottom:
                    target = (ny * width + nx) * 3
                    for channel in range(3):
                        data[target + channel] = max(0, min(255, data[target + channel] + error[channel]))
    result = Image.frombytes('P', (width, height), bytes(indices))
    result.putpalette([component for color in PALETTE for component in color] + [0] * (768 - 12))
    return result


def pack_pixels(indexed):
    if indexed.mode != 'P' or indexed.width % 4:
        raise ValueError('Expected a palette image with width divisible by four')
    pixels = indexed.tobytes()
    if any(pixel > 3 for pixel in pixels):
        raise ValueError('Only black/white/yellow/red indices 0..3 are allowed')
    return bytes((pixels[i] << 6) | (pixels[i + 1] << 4) | (pixels[i + 2] << 2) | pixels[i + 3]
                 for i in range(0, len(pixels), 4))


def prepare_image(path: Path):
    with Image.open(path) as image:
        fitted, bounds = fit_image(image)
    indexed = atkinson(fitted, bounds)
    packed = pack_pixels(indexed)
    assert len(packed) == FRAME_BYTES
    return packed, indexed.convert('RGB')
