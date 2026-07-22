/* Shared plumbing for the four GTK4 bench apps (hello / list / forms /
 * textview). See the repo README for the cross-framework spec. */
#pragma once

#include <glib.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef enum {
    BENCH_MODE_DEFAULT,
    BENCH_MODE_STARTUP,
    BENCH_MODE_SCROLL,
    BENCH_MODE_INTERACT,
} BenchMode;

static inline BenchMode bench_parse_mode(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--startup") == 0) return BENCH_MODE_STARTUP;
        if (strcmp(argv[i], "--scroll-bench") == 0) return BENCH_MODE_SCROLL;
        if (strcmp(argv[i], "--interact") == 0) return BENCH_MODE_INTERACT;
    }
    return BENCH_MODE_DEFAULT;
}

static inline double bench_env_f(const char *name, double dflt) {
    const char *v = getenv(name);
    if (!v) return dflt;
    char *end = NULL;
    double d = g_strtod(v, &end);
    return end != v ? d : dflt;
}

/* Scroll-bench duration; overridable so the harness controls pass length. */
static inline double bench_scroll_seconds(void) {
    return bench_env_f("BENCH_SCROLL_SECONDS", 6.0);
}

static inline int bench_interact_cycles(void) {
    return (int)bench_env_f("BENCH_INTERACT_CYCLES", 4.0);
}

static inline const char *bench_corpus_path(void) {
    const char *v = getenv("BENCH_CORPUS");
    return v ? v : "harness/out/corpus.txt";
}

static inline double bench_bounce(double dist, double max) {
    if (max <= 0.0) return 0.0;
    double period = 2.0 * max;
    double m = fmod(dist, period);
    return m < max ? m : period - m;
}

static inline void bench_print_first_frame(void) {
    printf("first_frame\n");
    fflush(stdout);
}

/* now/t0 are g_get_monotonic_time() microseconds. */
static inline void bench_print_startup_and_exit(gint64 t0_us, gint64 now_us) {
    printf("startup_ms: %.3f\n", (double)(now_us - t0_us) / 1000.0);
    fflush(stdout);
    exit(0);
}

/* Dump per-frame deltas + `done`, then KEEP RUNNING (the harness samples
 * post-run memory from the still-live process, then kills it). */
static inline void bench_print_deltas_done(GArray *frame_times_us) {
    for (guint i = 1; i < frame_times_us->len; i++) {
        gint64 a = g_array_index(frame_times_us, gint64, i - 1);
        gint64 b = g_array_index(frame_times_us, gint64, i);
        printf("%.3f\n", (double)(b - a) / 1000.0);
    }
    printf("done\n");
    fflush(stdout);
}
