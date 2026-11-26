"""Render a density view and deliver unmarked native-pixel evidence."""

import csv
from io import StringIO

import numpy as np
from PIL import Image

from .density import crop, reference, signal
from .photo import encode


def density_preview(rgb, settings):
    lane = settings["lane"]
    view = np.rint(np.clip(0.73 * rgb + 39, 0, 255)).astype(np.uint8)
    output = crop(view, lane)
    density = signal(crop(rgb, lane), reference(rgb, settings))
    light = np.clip(density / max(settings["threshold"] * 4, .32), 0, 1)
    start = np.array([242., 237., 214.])
    end = np.array([48., 47., 136.])
    output[:] = np.rint(start + light[:, :, None] * (end - start)).astype(np.uint8)
    return encode(Image.fromarray(view, "RGB"))


def strip_png(rgb, settings):
    return encode(Image.fromarray(crop(rgb, settings["lane"]), "RGB"))


def trace_csv(report):
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(("source_y", "rf", "density", "red_density", "green_density", "blue_density"))
    writer.writerows(
        (row["y"], f'{row["rf"]:.6f}', row["density"], *row["channels"]) for row in report["rows"]
    )
    return stream.getvalue().encode("utf-8")
