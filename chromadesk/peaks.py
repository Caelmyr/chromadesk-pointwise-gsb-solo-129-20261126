"""Evidence-aware peak reviews on the original, unmodified RGB grid.

A sampled RGB channel of zero is a censored measurement: its optical density is
at least the value obtained with the usual denominator floor of one.  Such a row
can therefore still be the darkest row on the full adopted strip width.  When
several rows are compared, every row must be scored on exactly the same original
columns.  Columns where any candidate has a zero channel are excluded from the
narrow, actually-measured comparison.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from .coordinates import migration
from .density import RGB_WEIGHTS, optical, reference


# Float32 conversion in the density pipeline can leave tiny differences.  Five
# decimal places are also the precision exposed by the existing report.
TIE_EPS = 5e-6


def span(left: int, right: int) -> dict[str, Any]:
    """Describe a half-open source-image column span."""
    left = int(left)
    right = int(right)
    return {
        "left": left,
        "right": right,
        "first_x": left,
        "last_x": right - 1,
        "count": max(0, right - left),
        "half_open": f"[{left}, {right})",
        "source": f"原片第 {left}–{right - 1} 列（半开区间 [{left}, {right})）",
    }


def _column_span_from_indices(indices: np.ndarray) -> dict[str, Any] | None:
    if indices.size == 0:
        return None
    return span(int(indices[0]), int(indices[-1]) + 1)


def contiguous_ranges(indices: Iterable[int] | np.ndarray) -> list[dict[str, Any]]:
    """Return compressed half-open ranges for sorted original column indices."""
    values = np.asarray(list(indices), dtype=np.int64)
    if values.size == 0:
        return []
    values = np.unique(values)
    breaks = np.flatnonzero(np.diff(values) > 1)
    starts = np.r_[values[0], values[breaks + 1]]
    ends = np.r_[values[breaks], values[-1]] + 1
    return [span(int(start), int(end)) for start, end in zip(starts, ends)]


def common_column_evidence(rgb: np.ndarray, ys: list[int], left: int, right: int) -> dict[str, Any]:
    """Columns where every requested row has all three RGB channels non-zero."""
    if not ys or right <= left:
        valid = np.zeros(max(0, right - left), dtype=bool)
    else:
        rows = rgb[np.asarray(ys, dtype=int), left:right, :]
        valid = np.all(rows > 0, axis=(0, 2))

    local_indices = np.flatnonzero(valid)
    columns = (local_indices + left).astype(int)
    ranges = contiguous_ranges(columns)
    widest = max(ranges, key=lambda item: (item["count"], -item["left"]), default=None)
    bounding = _column_span_from_indices(columns)
    if ranges:
        if len(ranges) == 1:
            source = ranges[0]["source"]
        else:
            listed = "、".join(f"{item['left']}–{item['last_x']}" for item in ranges)
            source = f"原片共同原列 {listed}；共 {int(columns.size)} 列（{len(ranges)} 个连续段）"
    else:
        source = "无共同完整可见原列"
    return {
        "readable": bool(columns.size),
        "left": int(columns[0]) if columns.size else None,
        "right": int(columns[-1]) + 1 if columns.size else None,
        "first_x": int(columns[0]) if columns.size else None,
        "last_x": int(columns[-1]) if columns.size else None,
        "count": int(columns.size),
        "columns": columns.tolist(),
        "ranges": ranges,
        "source": source,
        "bounding_span": bounding,
        # The widest segment is available when a single contiguous piece of
        # original imagery is preferable to the complete common-column set.
        "readable_range": widest,
        "widest_range": widest,
    }


def row_evidence(
    rgb: np.ndarray,
    white: np.ndarray,
    y: int,
    columns: slice | np.ndarray,
    absolute: bool = True,
) -> dict[str, Any]:
    """Score one row on the supplied original columns.

    ``columns`` is normally a half-open slice or an array of absolute original
    column indices.  The zero mask is retained so callers can distinguish an
    exact score from a lower bound.
    """
    if isinstance(columns, slice):
        left = 0 if columns.start is None else int(columns.start)
        right = rgb.shape[1] if columns.stop is None else int(columns.stop)
        pixels = rgb[y, left:right, :]
        source_columns = np.arange(left, right)
    else:
        source_columns = np.asarray(columns, dtype=int)
        pixels = rgb[y, source_columns, :]

    zero_mask = pixels == 0
    channel_clipped = np.any(zero_mask, axis=0).astype(bool).tolist()
    clipped_channels = np.flatnonzero(channel_clipped).astype(int).tolist()
    clipped_channel_names = ["RGB"[i] for i in clipped_channels]
    density = optical(pixels, white)
    channel_density = density.mean(axis=0, dtype=np.float64)
    score = float(channel_density @ RGB_WEIGHTS)
    zero_pixels = int(np.any(zero_mask, axis=1).sum())
    zero_channel_samples = int(zero_mask.sum())

    return {
        "y": int(y),
        "row": int(y),
        "density": round(score, 5),
        "lower_density": round(score, 5),
        "minimum_density": round(score, 5),
        "score": score,
        "channel_density": np.round(channel_density, 5).tolist(),
        "channel_density_lower": np.round(channel_density, 5).tolist(),
        "channel_clipped": channel_clipped,
        "zero_channels": clipped_channel_names,
        "clipped": bool(zero_channel_samples),
        "censored": bool(zero_channel_samples),
        "zero_channel": bool(zero_channel_samples),
        "zero_pixels": zero_pixels,
        "zero_channel_samples": zero_channel_samples,
        "clipped_channels": clipped_channels,
        "columns": source_columns.astype(int).tolist() if source_columns.size <= 4096 else [],
        "column_count": int(source_columns.size),
    }


def _dominator(rows: list[dict[str, Any]], target: dict[str, Any]) -> dict[str, Any] | None:
    best = None
    for other in rows:
        if other["y"] == target["y"]:
            continue
        if best is None or other["score"] > best["score"]:
            best = other
    if best is None:
        return None
    if best["score"] > target["score"] + TIE_EPS:
        return best
    return None


def _unique_maximum(
    items: list[dict[str, Any]],
    score_key: str = "score",
) -> tuple[dict[str, Any] | None, list[int]]:
    if not items:
        return None, []
    highest = max(item[score_key] for item in items)
    tied = [item for item in items if highest - item[score_key] <= TIE_EPS]
    if len(tied) == 1:
        return tied[0], []
    return None, [int(item["y"]) for item in tied]


def review_band(
    rgb: np.ndarray,
    settings: dict[str, Any],
    band: dict[str, Any],
    white: np.ndarray | None = None,
) -> dict[str, Any]:
    """Review one recognized band without treating an argmax as known truth."""
    if white is None:
        white = reference(rgb, settings)

    lane = settings["lane"]
    left, right = int(lane["left"]), int(lane["right"])
    first_y = int(band.get("first_y", band.get("first", band.get("start_y"))))
    last_y = int(band.get("last_y", band.get("last", band.get("end_y"))))
    if last_y < first_y:
        first_y, last_y = last_y, first_y

    height = int(rgb.shape[0])
    first_y = max(0, min(first_y, height - 1))
    last_y = max(0, min(last_y, height - 1))
    ys = list(range(first_y, last_y + 1))

    rows = [row_evidence(rgb, white, y, slice(left, right)) for y in ys]

    # A row containing a zero channel has no finite upper density bound, so it
    # cannot be excluded from the "could still be darkest" set.  An exact row
    # can be excluded only when another row's lower bound is already greater.
    candidates: list[int] = []
    excluded: list[dict[str, Any]] = []
    for item in rows:
        dominator = None if item["clipped"] else _dominator(rows, item)
        if dominator is None:
            candidates.append(item["y"])
        else:
            excluded.append({
                "y": item["y"],
                "row": item["y"],
                "because_y": dominator["y"],
                "dominated_by_y": dominator["y"],
                "margin": round(dominator["score"] - item["score"], 5),
                "reason": "another row's lower density bound is already greater",
            })

    common = common_column_evidence(rgb, candidates, left, right)

    measured_peak: dict[str, Any] | None = None
    common_columns = np.asarray(common.get("columns", []), dtype=int)

    if common_columns.size > 0:
        measured_rows = [row_evidence(rgb, white, y, common_columns) for y in candidates]
        winner, tied_ys = _unique_maximum(measured_rows)
        column_descriptor = {k: v for k, v in common.items() if k != "columns"}
        column_descriptor["column_count"] = int(common_columns.size)
        if winner is not None:
            y = winner["y"]
            measured_peak = {
                "status": "measured",
                "known": True,
                "y": y,
                "row": y,
                "peak_y": y,
                "rf": migration(y, settings),
                "density": round(winner["score"], 5),
                "columns": column_descriptor,
                "column_range": [common["left"], common["right"]],
                "column_ranges": common["ranges"],
                "used_columns": common["columns"],
                "contiguous_range": common.get("readable_range"),
                "scope": "all_common_readable_columns",
                "tied_ys": [],
                "message": f"窄范围实测峰在原行 {y}，使用{common['source']}。",
            }
        else:
            measured_peak = {
                "status": "undetermined",
                "known": False,
                "y": None,
                "row": None,
                "peak_y": None,
                "rf": None,
                "density": None,
                "columns": column_descriptor,
                "column_range": [common["left"], common["right"]],
                "column_ranges": common["ranges"],
                "used_columns": common["columns"],
                "contiguous_range": common.get("readable_range"),
                "scope": "all_common_readable_columns",
                "tied_ys": tied_ys,
                "message": "候选行在全部共同完整可见原列上仍同分，窄范围实测峰未定。",
            }
    else:
        measured_peak = {
            "status": "undetermined",
            "known": False,
            "y": None,
            "row": None,
            "peak_y": None,
            "rf": None,
            "density": None,
            "columns": None,
            "column_range": None,
            "scope": "common_readable_columns",
            "tied_ys": candidates,
            "message": "候选行没有共同完整可见原列，窄段实测峰未定。",
        }

    # Is there one row that is guaranteed to be deepest over the whole adopted
    # strip width?  A sole censored candidate is evidenced but only as a lower
    # density bound.
    by_y = {item["y"]: item for item in rows}
    broad_y: int | None = candidates[0] if len(candidates) == 1 else None
    broad_row = by_y.get(broad_y) if broad_y is not None else None
    if broad_y is None:
        broad_status = "undetermined"
        broad_message = "整带宽度上仍有多行可能最深，峰未定；可查看共同原列的窄段实测。"
    elif broad_row is not None and broad_row["clipped"]:
        broad_status = "lower_bound"
        broad_message = f"原行 {broad_y} 已有更低下界之外的排他证据，但含 RGB 零通道，峰密度只能记作至少 {broad_row['lower_density']:.5f}。"
    else:
        broad_status = "exact"
        broad_message = f"原行 {broad_y} 在整带同批原列上有唯一最高实测密度。"

    result = {
        "status": broad_status if broad_y is not None else "undetermined",
        "peak_status": broad_status if broad_y is not None else "undetermined",
        "known": broad_y is not None,
        "peak_known": broad_y is not None,
        "peak_determined": broad_y is not None,
        "ambiguous": broad_y is None,
        "undetermined": broad_y is None,
        "peak_y": broad_y,
        "peak_row": broad_y,
        "y": broad_y,
        "rf": migration(broad_y, settings) if broad_y is not None else None,
        "density": round(broad_row["score"], 5) if broad_row is not None else None,
        "density_is_lower_bound": bool(broad_row and broad_row["clipped"]),
        "first_y": first_y,
        "last_y": last_y,
        "band_rows": ys,
        "candidate_ys": candidates,
        "candidate_rows": candidates,
        "peak_candidates": candidates,
        "peak_candidate_rows": candidates,
        "candidates": candidates,
        "possible_ys": candidates,
        "possible_rows": candidates,
        "excluded_ys": [item["y"] for item in excluded],
        "excluded_rows": excluded,
        "rows": [{k: v for k, v in item.items() if k != "columns"} for item in rows],
        "lane_columns": span(left, right),
        "comparison_columns": span(left, right),
        "same_columns": True,
        "common_columns": common,
        "common_readable_columns": common,
        "readable_columns": common,
        "common_column_range": [common["left"], common["right"]] if common["count"] else None,
        "readable_column_range": [common["left"], common["right"]] if common["count"] else None,
        "common_column_ranges": common["ranges"],
        "readable_range": common,
        "widest_readable_range": common.get("readable_range"),
        "measured_peak": measured_peak,
        "narrow_peak": measured_peak,
        "measured_peak_y": measured_peak.get("peak_y"),
        "common_peak_y": measured_peak.get("peak_y"),
        "narrow_peak_y": measured_peak.get("peak_y"),
        "measured_rf": measured_peak.get("rf"),
        "measured_density": measured_peak.get("density"),
        "column_peak": None,
        "message": broad_message,
    }
    # A convenient nested alias.  Keep canonical fields at top level too for
    # callers that expect either a review object or a peak object.
    result["peak"] = {
        "status": result["status"],
        "peak_status": result["peak_status"],
        "known": result["known"],
        "peak_y": broad_y,
        "y": broad_y,
        "rf": result["rf"],
        "density": result["density"],
        "density_is_lower_bound": result["density_is_lower_bound"],
        "candidate_ys": candidates,
        "candidate_rows": candidates,
        "readable_columns": common,
        "measured_peak": measured_peak,
        "message": broad_message,
    }
    result["evidenced_peak"] = (
        result["peak"] if result["known"]
        else measured_peak if measured_peak.get("known")
        else None
    )
    return result


def peak_at_column(
    rgb: np.ndarray,
    settings: dict[str, Any],
    x: int,
    band: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
    white: np.ndarray | None = None,
) -> dict[str, Any]:
    """Find an evidenced peak at one original column among reviewed candidates."""
    x = int(x)
    if white is None:
        white = reference(rgb, settings)
    if review is None:
        if band is None:
            raise ValueError("band or review is required")
        review = review_band(rgb, settings, band, white)

    lane = settings["lane"]
    left, right = int(lane["left"]), int(lane["right"])
    base = {
        "x": x,
        "column": x,
        "first_y": review["first_y"],
        "last_y": review["last_y"],
        "candidate_ys": review["candidate_ys"],
        "candidate_rows": review["candidate_rows"],
        "peak_candidates": review["candidate_ys"],
        "candidates": review["candidate_ys"],
        "readable": False,
        "status": "undetermined",
        "peak_status": "undetermined",
        "known": False,
        "peak_y": None,
        "y": None,
        "rf": None,
        "density": None,
        "scores": [],
        "zero_channels": [],
        "readable_range": None,
        "readable_column_range": None,
        "message": "峰未定。",
        "review": review,
    }

    if not left <= x < right:
        base.update(
            reason="column_outside_lane",
            message=f"原列 {x} 不在本次可读范围（已采用量带列为 {left}–{right - 1}）；峰未定，原 RGB 还能照常点读。",
        )
        return base

    candidates = review["candidate_ys"]
    blockers = []
    column_rows = []
    for y in candidates:
        evidence = row_evidence(rgb, white, y, np.array([x], dtype=int))
        column_rows.append(evidence)
        if evidence["clipped"]:
            rgb_value = rgb[y, x, :].astype(int).tolist()
            names = [name for name, value in zip("RGB", rgb_value) if value == 0]
            blockers.append({"y": y, "zero_channels": names, "rgb": rgb_value})

    readable_info = review.get("readable_columns", {})
    ranges = readable_info.get("ranges", []) if isinstance(readable_info, dict) else []
    x_range = next((item for item in ranges if item["left"] <= x < item["right"]), None)

    exact_rows = [item for item in column_rows if not item["clipped"]]
    clipped_rows = [item for item in column_rows if item["clipped"]]
    bounded_peak: dict[str, Any]
    if not clipped_rows:
        winner, tied_ys = _unique_maximum(column_rows)
        if winner is not None:
            bounded_peak = {
                "status": "exact", "known": True, "peak_y": winner["y"], "y": winner["y"],
                "density": round(winner["score"], 5), "density_is_lower_bound": False,
            }
        else:
            bounded_peak = {
                "status": "tie", "known": False, "peak_y": None, "y": None,
                "tied_ys": tied_ys, "density_is_lower_bound": False,
            }
    elif len(clipped_rows) == 1:
        clipped = clipped_rows[0]
        best_exact = max((item["score"] for item in exact_rows), default=-np.inf)
        if clipped["score"] > best_exact + TIE_EPS:
            bounded_peak = {
                "status": "lower_bound", "known": True, "peak_y": clipped["y"], "y": clipped["y"],
                "density": round(clipped["score"], 5), "density_is_lower_bound": True,
            }
        else:
            exact_winner, _ = _unique_maximum(exact_rows)
            tied = [clipped["y"]] + ([exact_winner["y"]] if exact_winner is not None else [])
            bounded_peak = {
                "status": "undetermined", "known": False, "peak_y": None, "y": None,
                "tied_ys": tied, "density_is_lower_bound": True,
            }
    else:
        bounded_peak = {
            "status": "undetermined", "known": False, "peak_y": None, "y": None,
            "tied_ys": [item["y"] for item in clipped_rows],
            "density_is_lower_bound": True,
        }
    base["bounded_peak"] = bounded_peak
    base["lower_bound_peak"] = bounded_peak

    if blockers:
        base.update(
            reason="column_not_readable",
            zero_channels=blockers,
            readable_range=x_range,
            message=f"原列 {x} 不在本次可读范围（候选行在该列有 RGB 零通道，无法作完整可见比较）；峰未定，原 RGB 还能照常点读。",
        )
        return base

    winner, tied_ys = _unique_maximum(column_rows)
    scores = [{"y": item["y"], "density": round(item["score"], 5)} for item in column_rows]
    base["scores"] = scores
    base["readable"] = True
    base["readable_range"] = x_range or span(x, x + 1)
    base["readable_column_range"] = [x, x + 1]

    if winner is None:
        base.update(
            reason="tie",
            tied_ys=tied_ys,
            message=f"原列 {x} 上候选行 {('、'.join(map(str, tied_ys)))} 仍分不出谁深；峰未定，原 RGB 还能照常点读。",
        )
        return base

    y = int(winner["y"])
    base.update(
        status="evidenced",
        peak_status="evidenced",
        known=True,
        peak_determined=True,
        peak_y=y,
        y=y,
        rf=migration(y, settings),
        density=round(winner["score"], 5),
        reason=None,
        message=f"原列 {x} 的有证峰在原行 {y}。",
    )
    return base


def review_bands(
    rgb: np.ndarray,
    settings: dict[str, Any],
    bands: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    white = reference(rgb, settings)
    return [review_band(rgb, settings, band, white) for band in bands]


def peak_candidates(
    rgb: np.ndarray,
    settings: dict[str, Any],
    band: dict[str, Any],
    white: np.ndarray | None = None,
) -> list[int]:
    """Return only rows that can still be deepest under zero-channel bounds."""
    return review_band(rgb, settings, band, white)["candidate_ys"]


def common_original_columns(
    rgb: np.ndarray,
    rows: list[int],
    left: int,
    right: int,
) -> dict[str, Any]:
    """Alias using the issue's wording for common fully visible source columns."""
    return common_column_evidence(rgb, rows, left, right)


_raw_peak_at_column = peak_at_column


def peak_at_column(*args: Any, **kwargs: Any) -> dict[str, Any]:
    result = _raw_peak_at_column(*args, **kwargs)
    known = bool(result.get("known"))
    result["peak_undetermined"] = not known
    result["undetermined"] = not known
    result["ambiguous"] = not known
    result["pending"] = not known
    result["has_evidenced_peak"] = known
    result["label"] = "有证峰" if known else "峰未定"
    result["peak"] = {
        "status": result.get("status"),
        "known": known,
        "peak_y": result.get("peak_y"),
        "y": result.get("y"),
        "rf": result.get("rf"),
        "density": result.get("density"),
        "candidate_ys": result.get("candidate_ys"),
        "reason": result.get("reason"),
        "message": result.get("message"),
    }
    return result


# Descriptive aliases for callers/tests using the issue's "recheck" vocabulary.
recheck_band = review_band
peak_review = review_band
review_peak = review_band
recheck_peak = review_band
peak_for_column = peak_at_column
column_peak = peak_at_column
recheck_column = peak_at_column
possible_peak_rows = peak_candidates
common_readable_columns = common_original_columns
