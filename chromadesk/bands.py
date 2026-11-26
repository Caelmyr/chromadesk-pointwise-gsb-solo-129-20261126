"""Extract contiguous above-threshold bands from the lane's mean density trace."""

import numpy as np

from .coordinates import migration
from .density import optical, reference, RGB_WEIGHTS
from .peaks import peak_at_column, review_band, review_bands

peak_review = review_band
recheck_peak = review_band
column_peak = peak_at_column


def band_runs(signal, threshold):
    on = signal >= threshold
    edges = np.flatnonzero(np.diff(np.r_[False, on, False]))
    return zip(edges[::2], edges[1::2])


def profile(rgb, settings):
    white = reference(rgb, settings)
    lane = settings["lane"]
    top = settings["front"]
    bottom = settings["origin"] + 1
    scan = rgb[top:bottom, lane["left"]:lane["right"]]
    channels = optical(scan, white).mean(axis=1, dtype=np.float64)
    signal = channels @ RGB_WEIGHTS
    rows = []
    for i, density in enumerate(signal):
        absolute = top + i
        rows.append(
            dict(y=absolute, rf=migration(absolute, settings), density=round(float(density), 5),
                 channels=channels[i].round(5).tolist())
        )
    bands = []
    for start, end in band_runs(signal, settings["threshold"]):
        if end - start < 3:
            continue
        band_signal = signal[start:end]
        peak = int(start + np.argmax(band_signal))
        weight = float(band_signal.sum())
        center = float(np.dot(band_signal, np.arange(top + start, top + end)) / weight)
        trace_peak_y = top + peak
        band = dict(
            first_y=top + int(start), last_y=top + int(end) - 1,
            trace_peak_y=trace_peak_y, argmax_y=trace_peak_y,
            width=int(end - start),
            trace_rf=migration(trace_peak_y, settings),
            centroid_rf=migration(center, settings),
            trace_density=round(float(signal[peak]), 5),
            area=round(weight, 5), rgb=np.median(scan[peak], axis=0).astype(int).tolist(),
        )
        review = review_band(rgb, settings, band, white)
        band["peak_review"] = review
        band["peak_review_summary"] = review["peak"]
        # The reviewed peak, rather than the raw trace argmax, is the public
        # peak field.  It is None when the original pixels do not give evidence
        # for one unique row.
        band.update(review)
        bands.append(band)
    peak_reviews = [band["peak_review"] for band in bands]
    return dict(
        white=white.tolist(), rows=rows, bands=bands, sampled_columns=scan.shape[1],
        peak_reviews=peak_reviews, peaks=peak_reviews,
        peak_policy={
            "zero_rgb_channel": "lower_bound_only",
            "row_comparison": "same_original_columns",
            "narrow_peak_columns": "common_columns_without_zero_channels",
            "undetermined_when": ["no_unique_evidence", "column_not_common_readable", "tie"],
        },
    )
