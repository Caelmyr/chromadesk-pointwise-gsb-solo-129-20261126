"""Extract contiguous above-threshold bands from the lane's mean density trace."""

import numpy as np

from .coordinates import migration
from .density import optical, reference, RGB_WEIGHTS


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
        bands.append(dict(
            first_y=top + int(start), last_y=top + int(end) - 1, peak_y=top + peak,
            width=int(end - start), rf=migration(top + peak, settings),
            centroid_rf=migration(center, settings), density=round(float(signal[peak]), 5),
            area=round(weight, 5), rgb=np.median(scan[peak], axis=0).astype(int).tolist(),
        ))
    return dict(white=white.tolist(), rows=rows, bands=bands, sampled_columns=scan.shape[1])
