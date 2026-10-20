#!/usr/bin/env python3
"""Generate a small, dependency-free OminX installer splash for GRUB and ISOLINUX."""

from __future__ import annotations

import argparse
import math
import struct
import zlib
from pathlib import Path

WIDTH = 1280
HEIGHT = 720

FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
}


def mix(first: tuple[int, int, int], second: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, amount))
    return tuple(round(a + (b - a) * amount) for a, b in zip(first, second))


def blend(pixel: tuple[int, int, int], color: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    return mix(pixel, color, alpha)


def set_pixel(pixels: bytearray, x: int, y: int, color: tuple[int, int, int]) -> None:
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        offset = (y * WIDTH + x) * 3
        pixels[offset : offset + 3] = bytes(color)


def blend_pixel(
    pixels: bytearray, x: int, y: int, color: tuple[int, int, int], alpha: float
) -> None:
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        offset = (y * WIDTH + x) * 3
        previous = tuple(pixels[offset : offset + 3])
        pixels[offset : offset + 3] = bytes(blend(previous, color, alpha))


def draw_circle(
    pixels: bytearray,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
    alpha: float = 1.0,
) -> None:
    radius_squared = radius * radius
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius_squared:
                blend_pixel(pixels, x, y, color, alpha)


def draw_line(
    pixels: bytearray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    width: int,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> None:
    steps = max(abs(x2 - x1), abs(y2 - y1), 1)
    radius = max(1, width // 2)
    offsets = [
        (dx, dy)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dx * dx + dy * dy <= radius * radius
    ]
    for step in range(steps + 1):
        amount = step / steps
        x = round(x1 + (x2 - x1) * amount)
        y = round(y1 + (y2 - y1) * amount)
        color = mix(start, end, amount)
        for dx, dy in offsets:
            blend_pixel(pixels, x + dx, y + dy, color, 1.0)


def draw_ring(
    pixels: bytearray,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    rotation: float,
    color: tuple[int, int, int],
    alpha: float,
    thickness: float = 0.012,
) -> None:
    angle = math.radians(rotation)
    cosine, sine = math.cos(angle), math.sin(angle)
    extent_x = abs(rx * cosine) + abs(ry * sine)
    extent_y = abs(rx * sine) + abs(ry * cosine)
    for y in range(max(0, int(cy - extent_y)), min(HEIGHT, int(cy + extent_y + 1))):
        for x in range(max(0, int(cx - extent_x)), min(WIDTH, int(cx + extent_x + 1))):
            dx, dy = x - cx, y - cy
            local_x = cosine * dx + sine * dy
            local_y = -sine * dx + cosine * dy
            distance = (local_x / rx) ** 2 + (local_y / ry) ** 2
            if abs(distance - 1.0) < thickness:
                blend_pixel(pixels, x, y, color, alpha)


def draw_text(
    pixels: bytearray,
    text: str,
    x: int,
    y: int,
    scale: int,
    color: tuple[int, int, int],
    spacing: int = 1,
) -> None:
    cursor = x
    for character in text.upper():
        if character == " ":
            cursor += scale * 4
            continue
        glyph = FONT.get(character)
        if glyph is None:
            cursor += scale * 6
            continue
        for row, pattern in enumerate(glyph):
            for column, lit in enumerate(pattern):
                if lit == "1":
                    for dy in range(scale):
                        for dx in range(scale):
                            set_pixel(pixels, cursor + column * scale + dx, y + row * scale + dy, color)
        cursor += scale * (5 + spacing)


def make_pixels(width: int, height: int) -> bytearray:
    global WIDTH, HEIGHT
    WIDTH, HEIGHT = width, height
    scale_x = width / 1280
    scale_y = height / 720
    scale = min(scale_x, scale_y)
    sx = lambda value: round(value * scale_x)
    sy = lambda value: round(value * scale_y)
    sw = lambda value: max(1, round(value * scale))

    pixels = bytearray(width * height * 3)
    top = (7, 16, 25)
    bottom = (17, 24, 43)
    mint = (48, 181, 165)
    blue = (58, 105, 177)

    for y in range(height):
        vertical = y / (height - 1)
        base = mix(top, bottom, vertical)
        for x in range(width):
            nx = x / width
            center_x = (nx - 0.76) / 0.48
            center_y = (vertical - 0.47) / 0.70
            radius = math.sqrt(center_x * center_x + center_y * center_y)
            glow = max(0.0, 1.0 - radius) ** 2
            color = mix(base, mint, glow * 0.18)
            color = mix(color, blue, glow * 0.13)
            if x % max(1, sx(64)) == 0 or y % max(1, sy(64)) == 0:
                color = mix(color, (136, 170, 190), 0.025)
            offset = (y * width + x) * 3
            pixels[offset : offset + 3] = bytes(color)

    draw_ring(pixels, sx(930), sy(370), sx(276), sy(174), -27, (91, 218, 204), 0.16, 0.014)
    draw_ring(pixels, sx(930), sy(370), sx(330), sy(218), -27, (142, 129, 225), 0.10, 0.010)
    draw_ring(pixels, sx(930), sy(370), sx(214), sy(133), 63, (96, 164, 219), 0.09, 0.009)

    for x, y, radius, color in (
        (717, 201, 3, (151, 240, 223)),
        (1148, 513, 3, (175, 170, 247)),
        (1065, 163, 2, (183, 218, 247)),
        (797, 545, 2, (107, 230, 208)),
        (1178, 316, 2, (198, 221, 255)),
        (852, 137, 2, (160, 210, 245)),
    ):
        draw_circle(pixels, sx(x), sy(y), sw(radius), color, 0.86)

    # Original OminX X-mark, drawn as clean vector-like strokes without a blur filter.
    draw_circle(pixels, sx(930), sy(370), sw(186), mint, 0.10)
    draw_line(
        pixels, sx(813), sy(253), sx(1047), sy(487), sw(40),
        (120, 236, 218), (82, 153, 235),
    )
    draw_line(
        pixels, sx(1047), sy(253), sx(813), sy(487), sw(40),
        (88, 188, 222), (153, 133, 239),
    )
    for y in range(sy(350), sy(391)):
        for x in range(sx(910), sx(951)):
            if abs(x - sx(930)) + abs(y - sy(370)) <= sw(28):
                set_pixel(pixels, x, y, (222, 255, 247))

    title_scale = sw(13)
    draw_text(pixels, "OMINX", sx(124), sy(143), title_scale, (234, 248, 250), spacing=2)
    draw_line(
        pixels, sx(129), sy(255), sx(316), sy(255), sw(3),
        (86, 223, 202), (91, 162, 238),
    )
    draw_text(
        pixels, "AURORA  LIVE INSTALL", sx(131), sy(289), sw(4),
        (157, 184, 194), spacing=2,
    )
    draw_text(
        pixels, "WELCOME TO YOUR NEXT WORKSPACE", sx(131), sy(337), sw(2),
        (111, 139, 153), spacing=1,
    )
    return pixels


def encode_png(pixels: bytearray, width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    stride = width * 3
    raw = b"".join(
        b"\x00" + pixels[row * stride : (row + 1) * stride]
        for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_output = Path(__file__).resolve().parents[1] / "config" / "bootloaders"
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output,
        help="bootloaders directory receiving GRUB and ISOLINUX splash images",
    )
    parser.add_argument(
        "--binary-output-dir",
        type=Path,
        default=None,
        help="binary includes directory receiving final ISO splash images",
    )
    args = parser.parse_args()
    binary_output_dir = args.binary_output_dir or (args.output_dir.parent / "includes.binary")

    images = (
        (args.output_dir / "grub-pc" / "splash.png", 1280, 720),
        (args.output_dir / "isolinux" / "splash.png", 640, 480),
        (binary_output_dir / "boot" / "grub" / "splash.png", 1280, 720),
        (binary_output_dir / "isolinux" / "splash.png", 640, 480),
    )
    for destination, width, height in images:
        destination.parent.mkdir(parents=True, exist_ok=True)
        png = encode_png(make_pixels(width, height), width, height)
        destination.write_bytes(png)
        print(f"Wrote {destination} ({width}x{height}, {len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
