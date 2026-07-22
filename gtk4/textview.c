/* Bench textview app - GTK4 (C) variant: the shared ~1 MiB corpus
 * (5,000 wrapped paragraphs) in a GtkTextView (the idiomatic GTK long-
 * document widget; it validates layout lazily around the viewport)
 * inside a GtkScrolledWindow.
 * First-presented-frame: GdkFrameClock "after-paint" on map.
 * Scroll-bench: a frame-clock tick callback advances the vadjustment
 * from wall-clock elapsed time; per-frame timestamps come from
 * "after-paint". */

#include <gtk/gtk.h>

#include <math.h>

#include "bench_common.h"

#define SPEED 1000.0 /* px/s */

static gint64 t0_us;
static gboolean mode_startup = FALSE;
static gboolean mode_scroll = FALSE;
static gboolean reported = FALSE;
static double duration_s = 6.0;

static gboolean first_frame_seen = FALSE;
static gint64 scroll_start_us = 0;
static GArray *frame_times = NULL; /* gint64, CLOCK_MONOTONIC us */
static GtkAdjustment *vadj = NULL;

static void on_after_paint(GdkFrameClock *clock, gpointer data) {
    (void)clock;
    (void)data;
    gint64 now = g_get_monotonic_time();
    if (!first_frame_seen) {
        first_frame_seen = TRUE;
        bench_print_first_frame();
        if (mode_startup) bench_print_startup_and_exit(t0_us, now);
        scroll_start_us = now;
        return;
    }
    if (mode_scroll && !reported) g_array_append_val(frame_times, now);
}

static gboolean on_tick(GtkWidget *widget, GdkFrameClock *clock,
                        gpointer data) {
    (void)widget;
    (void)clock;
    (void)data;
    if (!mode_scroll || !first_frame_seen || reported) return G_SOURCE_CONTINUE;
    gint64 now = g_get_monotonic_time();
    double elapsed = (double)(now - scroll_start_us) / 1e6;
    if (elapsed >= duration_s) {
        /* Stay alive for the post-run memory sample. */
        bench_print_deltas_done(frame_times);
        reported = TRUE;
        return G_SOURCE_CONTINUE;
    }
    double max =
        gtk_adjustment_get_upper(vadj) - gtk_adjustment_get_page_size(vadj);
    gtk_adjustment_set_value(vadj, bench_bounce(SPEED * elapsed, max));
    return G_SOURCE_CONTINUE;
}

static void on_map(GtkWidget *widget, gpointer data) {
    (void)data;
    GdkFrameClock *fc = gtk_widget_get_frame_clock(widget);
    g_signal_connect(fc, "after-paint", G_CALLBACK(on_after_paint), NULL);
}

static void activate(GtkApplication *app, gpointer data) {
    (void)data;

    GtkCssProvider *css = gtk_css_provider_new();
    gtk_css_provider_load_from_string(
        css, "label.app-title { font-weight: bold; font-size: 18px; }");
    gtk_style_context_add_provider_for_display(
        gdk_display_get_default(), GTK_STYLE_PROVIDER(css),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);

    GtkWidget *win = gtk_application_window_new(app);
    gtk_window_set_title(GTK_WINDOW(win), "Bench");
    gtk_window_set_default_size(GTK_WINDOW(win), 800, 600);

    GtkWidget *root = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);

    /* Header ------------------------------------------------------- */
    GtkWidget *header = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    gtk_widget_set_size_request(header, -1, 48);
    gtk_widget_set_margin_start(header, 8);
    gtk_widget_set_margin_end(header, 8);
    gtk_widget_set_margin_top(header, 8);
    gtk_widget_set_margin_bottom(header, 8);
    GtkWidget *title = gtk_label_new("Bench");
    gtk_widget_add_css_class(title, "app-title");
    gtk_box_append(GTK_BOX(header), title);

    /* Document ----------------------------------------------------- */
    gchar *corpus = NULL;
    gsize corpus_len = 0;
    if (!g_file_get_contents(bench_corpus_path(), &corpus, &corpus_len, NULL)) {
        fprintf(stderr, "cannot read corpus %s\n", bench_corpus_path());
        exit(1);
    }
    GtkWidget *tv = gtk_text_view_new();
    gtk_text_view_set_editable(GTK_TEXT_VIEW(tv), FALSE);
    gtk_text_view_set_cursor_visible(GTK_TEXT_VIEW(tv), FALSE);
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(tv), GTK_WRAP_WORD);
    gtk_text_view_set_left_margin(GTK_TEXT_VIEW(tv), 8);
    gtk_text_view_set_right_margin(GTK_TEXT_VIEW(tv), 8);
    GtkTextBuffer *buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(tv));
    gtk_text_buffer_set_text(buf, corpus, (int)corpus_len);
    g_free(corpus);

    GtkWidget *scrolled = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scrolled),
                                   GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scrolled), tv);
    gtk_widget_set_vexpand(scrolled, TRUE);
    vadj = gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(scrolled));

    gtk_box_append(GTK_BOX(root), header);
    gtk_box_append(GTK_BOX(root), scrolled);
    gtk_window_set_child(GTK_WINDOW(win), root);

    g_signal_connect(win, "map", G_CALLBACK(on_map), NULL);
    gtk_widget_add_tick_callback(win, on_tick, NULL, NULL);

    gtk_window_present(GTK_WINDOW(win));
}

int main(int argc, char **argv) {
    t0_us = g_get_monotonic_time();
    BenchMode mode = bench_parse_mode(argc, argv);
    mode_startup = (mode == BENCH_MODE_STARTUP);
    mode_scroll = (mode == BENCH_MODE_SCROLL);
    duration_s = bench_scroll_seconds();
    frame_times = g_array_sized_new(FALSE, FALSE, sizeof(gint64), 4096);

    GtkApplication *app = gtk_application_new(
        "org.lumen.benchcomp.gtk4.textview", G_APPLICATION_NON_UNIQUE);
    g_signal_connect(app, "activate", G_CALLBACK(activate), NULL);
    /* Pass argc=1 so GApplication never sees our custom flags. */
    int status = g_application_run(G_APPLICATION(app), 1, argv);
    g_object_unref(app);
    return status;
}
