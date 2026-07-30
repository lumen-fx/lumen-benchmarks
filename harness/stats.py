#!/usr/bin/env python3
"""Statistics helpers for the benchmark harness.

Pure functions only: every function here takes numbers and returns numbers
or plain dicts, so they are testable without a display, a compositor, or a
build (see test_stats.py). The harness (bench.py) and the report generator
both use them, so a number in results.md is computed by the same code that
recorded it.

Definitions used throughout, in plain language:

* median: the middle value. Half the samples are below it, half above.
  Preferred over the mean because one slow launch cannot drag it around.
* IQR (interquartile range): the width of the middle half of the samples,
  q3 - q1. A spread measure that ignores the extremes.
* MAD (median absolute deviation): the median distance of a sample from
  the median. A second spread measure, even less sensitive to extremes
  than the IQR.
* min: the fastest/smallest sample observed. Treated as the noise floor:
  no amount of extra measurement makes a run faster than the work it has
  to do, so min is the closest thing to "the cost without interference".
* Tukey fences: the outlier rule. Anything below q1 - 1.5*IQR or above
  q3 + 1.5*IQR is called an outlier. Outliers are counted and reported,
  never dropped.
* bootstrap confidence interval: resample the recorded samples with
  replacement many times, take the median of each resample, and report
  the middle 95% of those medians. It answers "if this cell were measured
  again, where would the median plausibly land". Two frameworks whose
  intervals overlap are not separated by the data.
"""

import math
import random
import statistics

# Deterministic by default: the same samples produce the same confidence
# interval on every run and every machine.
DEFAULT_SEED = 20260101
DEFAULT_RESAMPLES = 10000
DEFAULT_CONFIDENCE = 0.95
# Below this many samples a bootstrap interval is not informative, so none
# is reported.
MIN_CI_SAMPLES = 5
# Tukey fence multiplier.
OUTLIER_K = 1.5


def percentile(values, p):
    """Nearest-rank percentile of `values` (0 < p <= 100)."""
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1,
              max(0, int(round(p / 100.0 * len(ordered))) - 1))
    return ordered[idx]


def quartiles(values):
    """(q1, median, q3). Single-sample input returns that sample three
    times, so the spread of a one-sample metric reads as zero."""
    if not values:
        return (None, None, None)
    if len(values) == 1:
        v = values[0]
        return (v, v, v)
    q = statistics.quantiles(values, n=4, method="inclusive")
    return (q[0], statistics.median(values), q[2])


def mad(values):
    """Median absolute deviation from the median."""
    if not values:
        return None
    med = statistics.median(values)
    return statistics.median([abs(v - med) for v in values])


def tukey_fences(values, k=OUTLIER_K):
    """(low, high) fence beyond which a sample counts as an outlier."""
    if not values:
        return (None, None)
    q1, _, q3 = quartiles(values)
    iqr = q3 - q1
    return (q1 - k * iqr, q3 + k * iqr)


def outliers(values, k=OUTLIER_K):
    """Samples outside the Tukey fences, in the order they were recorded."""
    lo, hi = tukey_fences(values, k)
    if lo is None:
        return []
    return [v for v in values if v < lo or v > hi]


def bootstrap_ci_median(values, confidence=DEFAULT_CONFIDENCE,
                        resamples=DEFAULT_RESAMPLES, seed=DEFAULT_SEED):
    """Percentile bootstrap confidence interval for the median.

    Draws `resamples` samples of the same size as `values`, with
    replacement, takes each one's median, and returns the middle
    `confidence` fraction of those medians as (low, high). Returns None
    when there are too few samples for the interval to mean anything.
    """
    n = len(values)
    if n < MIN_CI_SAMPLES:
        return None
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if resamples < 100:
        raise ValueError("resamples must be at least 100")
    rng = random.Random(seed)
    pick = rng.choices
    pool = list(values)
    half = n // 2
    odd = n % 2 == 1
    medians = []
    for _ in range(resamples):
        draw = sorted(pick(pool, k=n))
        medians.append(draw[half] if odd else (draw[half - 1] + draw[half]) / 2.0)
    medians.sort()
    tail = (1.0 - confidence) / 2.0
    lo_i = int(math.floor(tail * resamples))
    hi_i = min(resamples - 1, int(math.ceil((1.0 - tail) * resamples)) - 1)
    return (medians[lo_i], medians[hi_i])


def summarize(values, unstable_iqr_fraction=0.05, keep_samples=True,
              ci=False, confidence=DEFAULT_CONFIDENCE,
              resamples=DEFAULT_RESAMPLES, seed=DEFAULT_SEED, digits=3):
    """Robust summary of one metric's samples.

    Returns median, spread (IQR and MAD), min and max, the Tukey-fence
    outliers, and optionally a bootstrap confidence interval on the
    median. Raw samples are kept unless `keep_samples` is False, so any
    other statistic can be recomputed later without measuring again.
    """
    vals = [float(v) for v in values]
    if not vals:
        return {"n": 0}
    q1, med, q3 = quartiles(vals)
    iqr = q3 - q1
    outs = outliers(vals)
    out = {
        "n": len(vals),
        "median": round(med, digits),
        "min": round(min(vals), digits),
        "max": round(max(vals), digits),
        "q1": round(q1, digits),
        "q3": round(q3, digits),
        "iqr": round(iqr, digits),
        "mad": round(mad(vals), digits),
        "outliers": [round(v, digits) for v in outs],
        "n_outliers": len(outs),
        "unstable": bool(med) and abs(iqr / med) > unstable_iqr_fraction,
    }
    if keep_samples:
        out["samples"] = [round(v, digits) for v in vals]
    if ci:
        interval = bootstrap_ci_median(vals, confidence=confidence,
                                       resamples=resamples, seed=seed)
        if interval is not None:
            out["ci_low"] = round(interval[0], digits)
            out["ci_high"] = round(interval[1], digits)
            out["ci_level"] = confidence
            out["ci_resamples"] = resamples
            out["ci_method"] = "percentile bootstrap on the median"
    return out


def samples_of(summary):
    """Recorded samples of a summary dict, whichever key holds them.

    Schema 1 stored them under `runs`, schema 2 under `samples`."""
    if not isinstance(summary, dict):
        return []
    return summary.get("samples") or summary.get("runs") or []


def ensure_ci(summary, confidence=DEFAULT_CONFIDENCE,
              resamples=DEFAULT_RESAMPLES, seed=DEFAULT_SEED, digits=3):
    """Fill in min/MAD/confidence interval from the stored samples when a
    summary predates them. Returns a new dict; the input is not modified.

    This is what lets the report generator render an old results.json in
    the current format: schema 1 kept the raw samples, so everything the
    current report shows can be recomputed from them.
    """
    if not isinstance(summary, dict) or not summary:
        return summary
    out = dict(summary)
    vals = samples_of(out)
    if not vals:
        return out
    if out.get("min") is None:
        out["min"] = round(min(vals), digits)
    if out.get("max") is None:
        out["max"] = round(max(vals), digits)
    if out.get("mad") is None:
        out["mad"] = round(mad(vals), digits)
    if out.get("n_outliers") is None:
        out["n_outliers"] = len(out.get("outliers") or outliers(vals))
    if out.get("ci_low") is None:
        interval = bootstrap_ci_median(vals, confidence=confidence,
                                       resamples=resamples, seed=seed)
        if interval is not None:
            out["ci_low"] = round(interval[0], digits)
            out["ci_high"] = round(interval[1], digits)
            out["ci_level"] = confidence
            out["ci_resamples"] = resamples
            out["ci_method"] = "percentile bootstrap on the median"
    return out


def ci_bounds(summary):
    """(low, high) of a summary's confidence interval, or None."""
    if not isinstance(summary, dict):
        return None
    lo, hi = summary.get("ci_low"), summary.get("ci_high")
    if lo is None or hi is None:
        return None
    return (lo, hi)


def intervals_overlap(a, b):
    """True when two (low, high) intervals share any value.

    Overlapping intervals mean the two cells are not separated by the
    data: the difference between their medians is inside the measurement
    noise, so it should not be read as one being faster than the other.
    """
    if a is None or b is None:
        return False
    return a[0] <= b[1] and b[0] <= a[1]


def rel_diff(a, b):
    """Symmetric relative difference of two values, as a fraction.

    |a - b| divided by the average of the two, so neither value is
    privileged as the baseline. Returns None when both are zero.
    """
    if a is None or b is None:
        return None
    denom = (abs(a) + abs(b)) / 2.0
    if denom == 0:
        return None
    return abs(a - b) / denom


def agrees(a, b, tolerance):
    """True when two medians are within `tolerance` relative difference."""
    d = rel_diff(a, b)
    if d is None:
        return True
    return d <= tolerance
