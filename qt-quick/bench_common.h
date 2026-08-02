// Shared plumbing for the four Qt Quick bench apps (hello / list / forms /
// textview). See the repo README for the cross-framework spec.
#pragma once

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

using Clock = std::chrono::steady_clock; // CLOCK_MONOTONIC

enum class Mode { Default, Startup, ScrollBench, Interact };

inline Mode parseMode(int argc, char **argv) {
    if (argc > 1) {
        const std::string a = argv[1];
        if (a == "--startup") return Mode::Startup;
        if (a == "--scroll-bench") return Mode::ScrollBench;
        if (a == "--interact") return Mode::Interact;
    }
    return Mode::Default;
}

inline double envF(const char *name, double dflt) {
    const char *v = std::getenv(name);
    if (!v) return dflt;
    char *end = nullptr;
    double d = std::strtod(v, &end);
    return end != v ? d : dflt;
}

// Scroll-bench duration; overridable so the harness controls pass length.
inline double scrollSeconds() { return envF("BENCH_SCROLL_SECONDS", 6.0); }
inline int interactCycles() { return (int)envF("BENCH_INTERACT_CYCLES", 4.0); }

inline const char *corpusPath() {
    const char *v = std::getenv("BENCH_CORPUS");
    return v ? v : "harness/out/corpus.txt";
}

inline double bounce(double dist, double max) {
    if (max <= 0.0) return 0.0;
    const double period = 2.0 * max;
    double m = std::fmod(dist, period);
    return m < max ? m : period - m;
}

inline double msBetween(Clock::time_point a, Clock::time_point b) {
    return std::chrono::duration<double, std::milli>(b - a).count();
}

inline void printFirstFrame() {
    std::puts("first_frame");
    std::fflush(stdout);
}

[[noreturn]] inline void printStartupAndExit(Clock::time_point t0,
                                             Clock::time_point now) {
    std::printf("startup_ms: %.3f\n", msBetween(t0, now));
    std::fflush(stdout);
    std::exit(0);
}

// Dump per-frame deltas + `done`, then KEEP RUNNING (the harness samples
// post-run memory from the still-live process, then kills it).
inline void printDeltasDone(const std::vector<Clock::time_point> &frames) {
    std::string out;
    char buf[32];
    for (size_t i = 1; i < frames.size(); ++i) {
        std::snprintf(buf, sizeof buf, "%.3f\n",
                      msBetween(frames[i - 1], frames[i]));
        out += buf;
    }
    out += "done\n";
    std::fputs(out.c_str(), stdout);
    std::fflush(stdout);
}
