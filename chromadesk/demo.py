"""Generate labeled, repeatable practice scans of colored ink on paper."""

import numpy as np
from PIL import Image

from .photo import encode


EXERCISES = ("two-inks", "single-ink")
SIZE = (720, 540)


def practice(kind):
    width, height = SIZE
    y, x = np.mgrid[:height, :width]
    rng = np.random.default_rng(176)
    texture = rng.normal(0, 1.65, (height, width))
    base = np.array([242.0, 237.0, 219.0]) + texture[:, :, None] + ((x - 340) / 170 - (y - 270) / 290)[:, :, None]
    fibers = (np.sin(x * 1.51 + y * 0.07) + np.sin(y * 1.32 + x * 0.016)) * 0.71
    base += fibers[:, :, None]
    for center, spread, tint in (
        (281, 16, (101, 157, 39)),
        (350, 11, (22, 119, 117)),
        (205, 19, (43, 34, 4)),
    ):
        if kind == "single-ink" and center != 281:
            continue
        lane = np.clip(1 - ((x - 344) / 114) ** 6, 0, 1)
        displacement = 9 * np.sin((x - 244) / 34)
        transmission = np.exp(-0.5 * ((y - center - displacement) / spread) ** 2) * lane
        base -= transmission[:, :, None] * np.array(tint)
    base -= np.exp(-((y - 407.5) / 1.3) ** 2)[:, :, None] * np.array([25., 27., 23.])
    if kind == "two-inks":
        wet = 128 + 21 * np.sin((x - 229) / 84)
        visible = (x > 222) & (x < 478) & ((x < 352) | (x > 369))
        offset = 134 + (x - 280) * 0.018
        second_trace = np.exp(-0.5 * ((y - offset) / 1.2) ** 2) * (x > 250) * (x < 439)
        second_trace *= np.clip((x - 246) / 22, 0, 1) * np.clip((444 - x) / 22, 0, 1)
        base -= second_trace[:, :, None] * np.array([43., 20., 4.])
    else:
        wet = np.full_like(x, 128)
        visible = (x > 222) & (x < 478)
    base -= (np.exp(-0.5 * ((y - wet) / 1.5) ** 2) * visible)[:, :, None] * np.array([60., 30., 8.])
    outside = (x < 35 + (y - 200) / 140) | (x > 682 - y / 100) | (y < 33) | (y > 465)
    base[outside] = np.array([47., 54., 53.]) + texture[outside, None]
    image = Image.fromarray(np.uint8(np.clip(np.rint(base), 0, 255)), "RGB")
    settings = {
        "lane": {"left": 226, "top": 92, "right": 472, "bottom": 423},
        "paper": {"left": 109, "top": 180, "right": 198, "bottom": 385},
        "front": 128,
        "origin": 408,
        "threshold": 0.078,
    }
    return encode(image), settings
