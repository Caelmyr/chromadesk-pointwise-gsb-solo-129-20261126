"""Turn a requested migration fraction into a point to recheck in the native scan."""

from math import floor

from image_lab.validation import Invalid


def locate(settings, x, fraction):
    lane = settings["lane"]
    if not lane["left"] <= x < lane["right"]:
        raise Invalid("回查列须在已采用量带内")
    origin, front = settings["origin"], settings["front"]
    row = floor(origin - fraction * (origin - front) + 0.5)
    return x, row
