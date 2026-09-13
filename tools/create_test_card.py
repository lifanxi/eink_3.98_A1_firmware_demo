#!/usr/bin/env python3
"""Draw a calibration image with distinct corners, colors and center lines."""
from pathlib import Path
import argparse
from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
args = parser.parse_args()
image = Image.new('RGB', (1024, 640), 'white')
draw = ImageDraw.Draw(image)
font = ImageFont.load_default(size=32)
small = ImageFont.load_default(size=24)
draw.rectangle((0, 0, 1023, 639), outline='black', width=5)
draw.text((25, 18), 'TOP LEFT  A', font=font, fill='black')
draw.text((745, 18), 'B  TOP RIGHT', font=font, fill='black')
draw.text((25, 592), 'BOTTOM LEFT  C', font=small, fill='black')
draw.text((762, 592), 'D  BOTTOM RIGHT', font=small, fill='black')
draw.text((245, 82), 'InkBLE  123456789  ->', font=font, fill='black')
colors = [('BLACK', (0, 0, 0)), ('WHITE', (255, 255, 255)), ('YELLOW', (232, 176, 0)), ('RED', (200, 0, 0))]
for i, (label, rgb) in enumerate(colors):
    x = 35 + i * 240
    draw.rectangle((x, 150, x + 228, 270), fill=rgb, outline='black', width=2)
    draw.text((x + 20, 281), label, font=small, fill='black')
for x in range(40, 984):
    value = round((x - 40) * 255 / 943)
    draw.line((x, 325, x, 395), fill=(value, value, value))
    draw.line((x, 405, x, 475), fill=(255 - value, value, 128))
for y in range(500, 574, 12): draw.line((30, y, 994, y), fill='black', width=2)
for x in range(30, 995, 24): draw.line((x, 500, x, 573), fill='black', width=2)
draw.line((30, 573, 994, 500), fill=(200, 0, 0), width=4)
image.save(args.output)
