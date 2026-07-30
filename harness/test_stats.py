#!/usr/bin/env python3
"""Tests for the statistics helpers and the report formatting.

Synthetic data only: no display, no compositor, no build, no measurement.
Run with the same interpreter as the harness:

    python3 harness/test_stats.py
    python3 -m unittest discover -s harness -p 'test_*.py'
"""

import statistics
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import bench  # noqa: E402
import stats  # noqa: E402


class TestPointEstimates(unittest.TestCase):
    def test_percentile_nearest_rank(self):
        vals = list(range(1, 101))  # 1..100
        self.assertEqual(stats.percentile(vals, 50), 50)
        self.assertEqual(stats.percentile(vals, 95), 95)
        self.assertEqual(stats.percentile(vals, 99), 99)
        self.assertEqual(stats.percentile(vals, 100), 100)

    def test_percentile_of_empty_is_none(self):
        self.assertIsNone(stats.percentile([], 50))

    def test_quartiles_of_known_sample(self):
        # 1..9: middle half spans 3..7, median 5.
        q1, med, q3 = stats.quartiles(list(range(1, 10)))
        self.assertEqual(med, 5)
        self.assertEqual(q1, 3)
        self.assertEqual(q3, 7)

    def test_quartiles_of_single_sample_have_no_spread(self):
        self.assertEqual(stats.quartiles([4.0]), (4.0, 4.0, 4.0))

    def test_mad_of_known_sample(self):
        # distances from the median (5) are 4,3,2,1,0,1,2,3,4 -> median 2.
        self.assertEqual(stats.mad(list(range(1, 10))), 2)

    def test_mad_barely_moves_when_one_extreme_value_arrives(self):
        base = [10.0 + i * 0.1 for i in range(21)]
        spiked = base + [1000.0]
        mad_shift = abs(stats.mad(spiked) - stats.mad(base))
        sd_shift = abs(statistics.pstdev(spiked) - statistics.pstdev(base))
        self.assertLess(mad_shift, 0.2)
        self.assertGreater(sd_shift, 100.0)


class TestOutliers(unittest.TestCase):
    def test_tukey_fences_flag_the_far_sample(self):
        vals = [10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 40.0]
        found = stats.outliers(vals)
        self.assertEqual(found, [40.0])

    def test_clean_sample_has_no_outliers(self):
        self.assertEqual(stats.outliers([5.0, 5.1, 5.2, 5.3, 5.4]), [])

    def test_outliers_stay_in_the_summary_samples(self):
        vals = [10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 40.0]
        summary = stats.summarize(vals)
        self.assertEqual(summary["n_outliers"], 1)
        self.assertIn(40.0, summary["samples"])
        self.assertEqual(summary["n"], len(vals))


class TestSummarize(unittest.TestCase):
    def setUp(self):
        # A tight cluster with one slow launch, the shape a startup sample
        # usually has.
        self.vals = [50.0, 50.5, 51.0, 51.2, 51.5, 52.0, 52.5, 53.0, 80.0]

    def test_reports_median_min_max(self):
        s = stats.summarize(self.vals)
        self.assertEqual(s["median"], 51.5)
        self.assertEqual(s["min"], 50.0)
        self.assertEqual(s["max"], 80.0)
        self.assertEqual(s["n"], 9)

    def test_spread_is_robust_to_the_slow_launch(self):
        s = stats.summarize(self.vals)
        self.assertLess(s["iqr"], 5.0)
        self.assertLess(s["mad"], 2.0)

    def test_unstable_flag_follows_the_threshold(self):
        steady = [16.0, 16.1, 16.2, 16.3]
        noisy = [10.0, 20.0, 30.0, 40.0]
        self.assertFalse(stats.summarize(steady)["unstable"])
        self.assertTrue(stats.summarize(noisy)["unstable"])

    def test_empty_input_reports_no_samples(self):
        self.assertEqual(stats.summarize([]), {"n": 0})

    def test_samples_can_be_dropped_on_request(self):
        s = stats.summarize(self.vals, keep_samples=False)
        self.assertNotIn("samples", s)


class TestBootstrap(unittest.TestCase):
    def test_interval_brackets_the_median(self):
        vals = [50.0, 50.5, 51.0, 51.2, 51.5, 52.0, 52.5, 53.0]
        lo, hi = stats.bootstrap_ci_median(vals, resamples=2000)
        self.assertLessEqual(lo, statistics.median(vals))
        self.assertLessEqual(statistics.median(vals), hi)

    def test_same_seed_gives_the_same_interval(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        a = stats.bootstrap_ci_median(vals, seed=7, resamples=1000)
        b = stats.bootstrap_ci_median(vals, seed=7, resamples=1000)
        self.assertEqual(a, b)

    def test_tight_sample_gives_a_narrow_interval(self):
        tight = [50.0 + i * 0.01 for i in range(20)]
        wide = [50.0 + i * 5.0 for i in range(20)]
        t_lo, t_hi = stats.bootstrap_ci_median(tight, resamples=2000)
        w_lo, w_hi = stats.bootstrap_ci_median(wide, resamples=2000)
        self.assertLess(t_hi - t_lo, w_hi - w_lo)

    def test_too_few_samples_gets_no_interval(self):
        self.assertIsNone(stats.bootstrap_ci_median([1.0, 2.0]))

    def test_summarize_carries_the_interval_when_asked(self):
        vals = [float(v) for v in range(20)]
        s = stats.summarize(vals, ci=True, resamples=1000)
        self.assertLessEqual(s["ci_low"], s["median"])
        self.assertLessEqual(s["median"], s["ci_high"])
        self.assertEqual(s["ci_resamples"], 1000)


class TestOverlap(unittest.TestCase):
    def test_separated_intervals_do_not_overlap(self):
        self.assertFalse(stats.intervals_overlap((50.0, 52.0), (60.0, 62.0)))

    def test_touching_intervals_count_as_overlapping(self):
        self.assertTrue(stats.intervals_overlap((50.0, 60.0), (60.0, 70.0)))

    def test_nested_intervals_overlap(self):
        self.assertTrue(stats.intervals_overlap((50.0, 70.0), (55.0, 60.0)))

    def test_missing_interval_never_overlaps(self):
        self.assertFalse(stats.intervals_overlap(None, (1.0, 2.0)))

    def test_ci_bounds_reads_a_summary(self):
        s = stats.summarize([float(v) for v in range(20)], ci=True,
                            resamples=1000)
        self.assertEqual(stats.ci_bounds(s), (s["ci_low"], s["ci_high"]))
        self.assertIsNone(stats.ci_bounds({"median": 1.0}))


class TestRelativeDifference(unittest.TestCase):
    def test_identical_values_differ_by_zero(self):
        self.assertEqual(stats.rel_diff(50.0, 50.0), 0.0)

    def test_difference_is_symmetric(self):
        self.assertEqual(stats.rel_diff(50.0, 55.0), stats.rel_diff(55.0, 50.0))

    def test_known_difference(self):
        # 10 vs 12: gap 2, average 11.
        self.assertAlmostEqual(stats.rel_diff(10.0, 12.0), 2.0 / 11.0)

    def test_agreement_follows_the_tolerance(self):
        self.assertTrue(stats.agrees(100.0, 104.0, 0.05))
        self.assertFalse(stats.agrees(100.0, 120.0, 0.05))


class TestSchemaCompatibility(unittest.TestCase):
    def test_samples_are_found_under_either_key(self):
        self.assertEqual(stats.samples_of({"runs": [1.0, 2.0]}), [1.0, 2.0])
        self.assertEqual(stats.samples_of({"samples": [3.0]}), [3.0])
        self.assertEqual(stats.samples_of({}), [])

    def test_old_summary_gains_min_mad_and_interval(self):
        vals = [50.0, 50.5, 51.0, 51.2, 51.5, 52.0, 52.5, 53.0]
        old = {"n": len(vals), "runs": vals, "median": 51.35, "q1": 50.875,
               "q3": 52.125, "iqr": 1.25, "outliers": [], "unstable": False}
        new = stats.ensure_ci(old, resamples=1000)
        self.assertEqual(new["min"], 50.0)
        self.assertIsNotNone(new["mad"])
        self.assertIsNotNone(new["ci_low"])
        self.assertNotIn("min", old)  # input untouched

    def test_enriching_without_samples_changes_nothing(self):
        old = {"median": 5.0}
        self.assertEqual(stats.ensure_ci(old), old)


class TestHarnessStats(unittest.TestCase):
    """The harness wrappers around the helpers."""

    def test_run_stats_keeps_warmup_samples_aside(self):
        s = bench.run_stats([10.0, 10.1, 10.2], warmup=[30.0])
        self.assertEqual(s["warmup_samples"], [30.0])
        self.assertEqual(s["warmup_discarded"], 1)
        self.assertNotIn(30.0, s["samples"])

    def test_frame_stats_discards_the_warmup_frames(self):
        deltas = [100.0] * 5 + [16.0] * 200
        s = bench.frame_stats(deltas, warmup_frames=5)
        self.assertEqual(s["warmup_frames"], 5)
        self.assertEqual(s["p50_ms"], 16.0)
        self.assertEqual(s["max_ms"], 16.0)
        self.assertEqual(s["frames"], 200)

    def test_frame_stats_keeps_every_raw_delta(self):
        deltas = [100.0] * 5 + [16.0] * 200
        s = bench.frame_stats(deltas, warmup_frames=5)
        self.assertEqual(len(s.get("samples_ms", [])), len(deltas))

    def test_frame_stats_keeps_a_short_pass_whole(self):
        s = bench.frame_stats([16.0] * 8, warmup_frames=5)
        self.assertEqual(s["warmup_frames"], 0)
        self.assertEqual(s["frames"], 8)

    def test_frame_stats_of_an_empty_pass(self):
        self.assertEqual(bench.frame_stats([])["frames"], 0)

    def test_combine_passes_medians_the_passes(self):
        passes = [bench.frame_stats([16.0] * 100, warmup_frames=0),
                  bench.frame_stats([17.0] * 100, warmup_frames=0),
                  bench.frame_stats([18.0] * 100, warmup_frames=0)]
        c = bench.combine_passes(passes)
        self.assertEqual(c["p50_ms_median"], 17.0)
        self.assertEqual(c["p50_ms_spread"], 2.0)
        self.assertEqual(c["p50_ms_min"], 16.0)
        self.assertEqual(c["frames_total"], 300)

    def test_mem_stats_summarizes_each_series(self):
        mems = [{"pss_kb": 1000, "rss_kb": 2000},
                {"pss_kb": 1100, "rss_kb": 2100},
                {"pss_kb": 1050, "rss_kb": 2050}]
        s = bench.mem_stats(mems)
        self.assertEqual(s["pss_kb"]["median"], 1050)
        self.assertEqual(s["pss_kb"]["min"], 1000)
        self.assertEqual(bench.median_mem(mems)["pss_kb"], 1050)


class TestFormatting(unittest.TestCase):
    def setUp(self):
        self.summary = stats.summarize(
            [50.0, 50.5, 51.0, 51.2, 51.5, 52.0, 52.5, 53.0, 80.0],
            ci=True, resamples=1000)

    def test_median_and_spread_render(self):
        self.assertTrue(bench.fmt_median(self.summary).startswith("51.5"))
        self.assertIn("(", bench.fmt_spread(self.summary))

    def test_outlier_marker_counts_the_outliers(self):
        self.assertIn("(1o)", bench.fmt_median(self.summary))

    def test_unstable_marker_appears(self):
        noisy = stats.summarize([10.0, 20.0, 30.0, 40.0])
        self.assertIn("(!)", bench.fmt_median(noisy))

    def test_confidence_interval_renders_as_a_range(self):
        self.assertIn("-", bench.fmt_ci(self.summary))
        self.assertEqual(bench.fmt_ci({}), "-")

    def test_missing_values_render_as_a_dash(self):
        self.assertEqual(bench.fmt_median({}), "-")
        self.assertEqual(bench.fmt_spread(None), "-")
        self.assertEqual(bench.fmt_ms(None), "-")
        self.assertEqual(bench.fmt_mem(None), "-")

    def test_frame_percentile_shows_median_spread_and_floor(self):
        metric = {"p50_ms_median": 16.67, "p50_ms_spread": 0.02,
                  "p50_ms_min": 16.66}
        self.assertEqual(bench.fmt_pct(metric, "p50_ms"),
                         "16.67 (0.02, min 16.66)")

    def test_frame_percentile_floor_comes_from_the_passes_when_missing(self):
        metric = {"p50_ms_median": 16.67, "p50_ms_spread": 0.02,
                  "passes": [{"p50_ms": 16.66}, {"p50_ms": 16.68}]}
        self.assertIn("min 16.66", bench.fmt_pct(metric, "p50_ms"))

    def test_memory_shows_pss_rss_and_spread(self):
        mems = [{"pss_kb": 51200, "rss_kb": 102400},
                {"pss_kb": 52224, "rss_kb": 103424},
                {"pss_kb": 51712, "rss_kb": 102912}]
        cell = bench.fmt_mem(bench.median_mem(mems), bench.mem_stats(mems))
        self.assertTrue(cell.startswith("50.5 +/-"))
        self.assertIn("(100.5)", cell)

    def test_memory_without_repeats_shows_no_spread(self):
        self.assertEqual(bench.fmt_mem({"pss_kb": 51200, "rss_kb": 102400}),
                         "50.0 (100.0)")


class TestOverlapReporting(unittest.TestCase):
    def test_only_overlapping_pairs_are_named(self):
        a = {"median": 50.0, "ci_low": 49.0, "ci_high": 51.0}
        b = {"median": 50.5, "ci_low": 50.0, "ci_high": 51.5}
        c = {"median": 90.0, "ci_low": 89.0, "ci_high": 91.0}
        pairs = bench.overlapping_pairs([("a", a), ("b", b), ("c", c)])
        self.assertEqual(pairs, [("a", "b")])

    def test_no_pairs_when_every_cell_is_separated(self):
        a = {"ci_low": 1.0, "ci_high": 2.0}
        b = {"ci_low": 3.0, "ci_high": 4.0}
        self.assertEqual(bench.overlapping_pairs([("a", a), ("b", b)]), [])


class TestAgreement(unittest.TestCase):
    def _results(self, run1, run2):
        def cell(startup, pss):
            return {"startup": {"external_ms": {"median": startup}},
                    "mem_idle": {"pss_kb": pss}}
        return {
            "config": {"agreement_tolerance": 0.05},
            "rounds": [
                {"cells": {"slint": {"hello": cell(run1, 50000)}}},
                {"cells": {"slint": {"hello": cell(run2, 50000)}}},
            ],
        }

    def test_close_runs_agree(self):
        rows = bench.agreement_rows(self._results(100.0, 102.0))
        startup = [r for r in rows if r["metric"] == "startup ext ms"][0]
        self.assertTrue(startup["agree"])
        self.assertAlmostEqual(startup["rel_diff"], 0.0198, places=3)

    def test_far_runs_disagree(self):
        rows = bench.agreement_rows(self._results(100.0, 130.0))
        startup = [r for r in rows if r["metric"] == "startup ext ms"][0]
        self.assertFalse(startup["agree"])

    def test_identical_memory_agrees(self):
        rows = bench.agreement_rows(self._results(100.0, 100.0))
        mem = [r for r in rows if r["metric"] == "idle PSS kB"][0]
        self.assertEqual(mem["rel_diff"], 0.0)
        self.assertTrue(mem["agree"])

    def test_one_run_produces_no_agreement_rows(self):
        one = {"rounds": [{"cells": {}}]}
        self.assertEqual(bench.agreement_rows(one), [])

    def test_tolerance_comes_from_the_recorded_config(self):
        r = self._results(100.0, 110.0)
        r["config"]["agreement_tolerance"] = 0.2
        rows = bench.agreement_rows(r)
        self.assertTrue(rows[0]["agree"])


class TestConfigCapture(unittest.TestCase):
    def test_every_knob_is_recorded(self):
        cfg = bench.config_block()
        for key in ("schema_version", "startup_runs", "startup_warmup_runs",
                    "frame_warmup_frames", "mem_runs", "calibration_runs",
                    "ci_confidence", "ci_resamples", "ci_seed",
                    "agreement_tolerance", "unstable_iqr_fraction",
                    "outlier_rule"):
            self.assertIn(key, cfg)

    def test_startup_default_supports_percentiles(self):
        self.assertGreaterEqual(bench.STARTUP_RUNS, 20)

    def test_env_knobs_parse(self):
        import os
        os.environ["BENCH_TEST_KNOB"] = "7"
        try:
            self.assertEqual(bench._env_int("BENCH_TEST_KNOB", 1), 7)
            self.assertEqual(bench._env_float("BENCH_TEST_KNOB", 1.0), 7.0)
            self.assertEqual(bench._env_int("BENCH_MISSING_KNOB", 3), 3)
            self.assertTrue(bench._env_bool("BENCH_MISSING_KNOB", True))
        finally:
            del os.environ["BENCH_TEST_KNOB"]

    def test_report_config_falls_back_for_old_results(self):
        rcfg = bench.report_config({"rounds": []})
        self.assertEqual(rcfg["schema"], 1)
        self.assertEqual(rcfg["confidence"], bench.CI_CONFIDENCE)

    def test_report_config_reads_recorded_settings(self):
        rcfg = bench.report_config({"schema_version": 2,
                                    "config": {"ci_confidence": 0.9,
                                               "agreement_tolerance": 0.1}})
        self.assertEqual(rcfg["confidence"], 0.9)
        self.assertEqual(rcfg["tolerance"], 0.1)
        self.assertEqual(rcfg["schema"], 2)

    def test_display_description_names_the_compositor(self):
        d = bench.Display()
        d.backend = "weston"
        d.command = ["weston", "--backend=headless"]
        desc = d.describe()
        self.assertEqual(desc["backend"], "weston")
        self.assertTrue(desc["nested_headless"])
        self.assertEqual(desc["refresh_hz"], 60)

    def test_report_text_is_ascii(self):
        # \u2022 is the bullet `flutter --version` prints.
        self.assertEqual(bench.ascii_only("Flutter 3.4 \u2022 stable"),
                         "Flutter 3.4 - stable")
        self.assertEqual(bench.ascii_only(None), "-")


class TestReportRendering(unittest.TestCase):
    """The generator renders both schema versions without measuring."""

    def _render(self, results):
        out = HERE / "out" / "test_results.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        old = bench.RESULTS_MD
        bench.RESULTS_MD = out
        try:
            bench.write_report(results, write_json=False)
            return out.read_text()
        finally:
            bench.RESULTS_MD = old
            out.unlink(missing_ok=True)

    def _schema1(self):
        samples = [50.0, 50.5, 51.0, 51.2, 51.5, 52.0, 52.5, 53.0]
        return {
            "generated": "2026-01-01 00:00:00 +0000",
            "env": {"hostname": "testhost", "cpu_model": "Test CPU",
                    "cpu_count": 8, "governors": ["performance"]},
            "display_backend": "weston",
            "rounds": [{"cells": {"slint": {"hello": {
                "startup": {"external_ms": {
                    "n": len(samples), "runs": samples, "median": 51.35,
                    "q1": 50.875, "q3": 52.125, "iqr": 1.25,
                    "outliers": [], "unstable": False}},
                "mem_idle": {"pss_kb": 51200, "rss_kb": 102400},
            }}}}],
        }

    def test_schema1_results_still_render(self):
        md = self._render(self._schema1())
        self.assertIn("Cross-framework benchmark results", md)
        self.assertIn("How to read these tables", md)
        self.assertIn("Startup detail", md)

    def test_schema1_gets_recomputed_interval_and_floor(self):
        md = self._render(self._schema1())
        self.assertIn("recomputed here from the stored samples", md)
        # min of the schema-1 samples, recomputed for the startup table.
        self.assertIn("50.0", md)

    def test_environment_block_is_present(self):
        md = self._render(self._schema1())
        self.assertIn("## Environment", md)
        self.assertIn("Test CPU", md)

    def test_agreement_section_appears_with_two_runs(self):
        r = self._schema1()
        r["rounds"].append({"cells": {"slint": {"hello": {
            "startup": {"external_ms": {"median": 60.0, "runs": [60.0],
                                        "iqr": 1.0}},
            "mem_idle": {"pss_kb": 51200, "rss_kb": 102400}}}}})
        md = self._render(r)
        self.assertIn("Run-to-run agreement", md)
        self.assertIn("Over threshold", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
