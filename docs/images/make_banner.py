"""Draws docs/images/banner.png from the launcher's original portal motif (no game art)."""
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H, S = 1280, 400, 2  # drawn at 2x, then downsampled for smooth lines
img = Image.new("RGB", (W * S, H * S), (12, 17, 24))
d = ImageDraw.Draw(img)
for i in range(6):  # nested portals, as in the launcher
    x, y = (880 + i * 26) * S, (70 + i * 28) * S
    w, h, k = (330 - i * 44) * S, (270 - i * 42) * S, 38 * S
    c = (91, 232, 218) if i == 5 else (26 + i * 7, 60 + i * 17, 66 + i * 17)
    d.line([(x, y), (x + w - k, y), (x + w, y + k), (x + w, y + h), (x, y + h), (x, y)], fill=c, width=4 * S, joint="curve")
fonts = Path(os.environ["WINDIR"]) / "Fonts"
title = ImageFont.truetype(str(fonts / "segoeuib.ttf"), 108 * S)
sub = ImageFont.truetype(str(fonts / "seguisb.ttf"), 34 * S)
small = ImageFont.truetype(str(fonts / "segoeui.ttf"), 26 * S)
d.rectangle((80 * S, 92 * S, 128 * S, 97 * S), fill=(91, 232, 218))
d.text((72 * S, 108 * S), "DISRUPTOR", font=title, fill=(236, 244, 247))
d.text((80 * S, 236 * S), "R E C O M P I L E D", font=sub, fill=(91, 232, 218))
d.text((80 * S, 296 * S), "The PlayStation original, rebuilt as a native Windows game.", font=small, fill=(152, 173, 185))
img.resize((W, H), Image.Resampling.LANCZOS).save(Path(__file__).with_name("banner.png"), optimize=True)
