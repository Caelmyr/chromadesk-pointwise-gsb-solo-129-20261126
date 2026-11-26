"""Measure relative optical density against the selected clean-paper patch."""

import numpy as np

from .coordinates import contains, migration


RGB_WEIGHTS = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def crop(array, box):
    return array[box["top"]:box["bottom"], box["left"]:box["right"]]


def reference(rgb, settings):
    patch = crop(rgb, settings["paper"])
    white = np.median(patch.reshape(-1, 3), axis=0)
    return np.maximum(white.astype(np.float32), 1)


def optical(rgb, white):
    return np.maximum(0, np.log10(white / np.maximum(rgb.astype(np.float32), 1)))


def signal(rgb, white):
    return optical(rgb, white) @ RGB_WEIGHTS


def read(rgb, settings, x, y):
    source = rgb[y, x]
    white = reference(rgb, settings)
    channels = optical(source, white)
    lane = settings["lane"]
    in_lane = contains(lane, x, y)
    fraction = migration(y, settings) if in_lane else None
    return {
        "x": x, "y": y, "rgb": source.tolist(), "white": white.tolist(),
        "channel_density": np.round(channels, 5).tolist(),
        "density": round(float(channels @ RGB_WEIGHTS), 5),
        "inside_lane": in_lane, "rf": fraction,
    }
