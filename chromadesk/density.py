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
    weighted = float(channels @ RGB_WEIGHTS)
    zero_mask = np.asarray(source) == 0
    zero_names = [name for name, is_zero in zip("RGB", zero_mask) if bool(is_zero)]
    lane = settings["lane"]
    in_lane = contains(lane, x, y)
    fraction = migration(y, settings) if in_lane else None
    return {
        "x": x, "y": y, "rgb": source.tolist(), "white": white.tolist(),
        "channel_density": np.round(channels, 5).tolist(),
        "channel_density_lower": np.round(channels, 5).tolist(),
        "channel_zero": zero_mask.astype(bool).tolist(),
        "channel_clipped": zero_mask.astype(bool).tolist(),
        "any_channel_clipped": bool(np.any(zero_mask)),
        "zero_channels": zero_names,
        "clipped": bool(zero_names),
        "censored": bool(zero_names),
        "density": round(weighted, 5),
        "density_lower_bound": round(weighted, 5),
        "minimum_density": round(weighted, 5),
        "at_least_density": round(weighted, 5),
        "density_is_lower_bound": bool(zero_names),
        "at_least": bool(zero_names),
        "inside_lane": in_lane, "rf": fraction,
    }
