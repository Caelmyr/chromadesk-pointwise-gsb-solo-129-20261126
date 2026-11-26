"""Use integer pixel centers and half-open spans throughout the desk."""

from image_lab.validation import Invalid, integer, number, object_value


def bounds(raw, size, label, minimum):
    raw = object_value(raw, label)
    width, height = size
    box = {
        "left": integer(raw.get("left"), f"{label}左边", 0, width - 1),
        "right": integer(raw.get("right"), f"{label}右边", 1, width),
        "top": integer(raw.get("top"), f"{label}上边", 0, height - 1),
        "bottom": integer(raw.get("bottom"), f"{label}下边", 1, height),
    }
    if box["right"] - box["left"] < minimum or box["bottom"] - box["top"] < minimum:
        raise Invalid(f"{label}宽高至少 {minimum} 像素")
    return box


def default_settings(size):
    width, height = size
    return {
        "lane": {"left": width // 4, "top": height // 8, "right": 3 * width // 4, "bottom": 7 * height // 8},
        "paper": {"left": 0, "top": height // 4, "right": width // 6, "bottom": 3 * height // 4},
        "origin": 3 * height // 4,
        "front": height // 5,
        "threshold": 0.055,
    }


def validate(raw, size):
    lane = bounds(raw.get("lane"), size, "量带", 5)
    paper = bounds(raw.get("paper"), size, "清纸框", 4)
    top, bottom = lane["top"], lane["bottom"] - 1
    front = integer(raw.get("front"), "湿线行", top, bottom - 4)
    origin = integer(raw.get("origin"), "加样原行", front + 4, bottom)
    threshold = number(raw.get("threshold"), "认带门槛", 0.005, 2.0)
    return dict(lane=lane, paper=paper, origin=origin, front=front, threshold=threshold)


def contains(box, x, y):
    return box["left"] <= x < box["right"] and box["top"] <= y < box["bottom"]


def migration(y, settings):
    bottom = settings["origin"]
    top = settings["front"]
    if y < top or y > bottom:
        return None
    return (bottom - y) / (bottom - top)
