/* Bench list app - GTK4 (C) variant. See repo README for the shared
 * spec (header + 10k-row virtualized GtkListView + footer).
 *
 * List: GtkListView + GtkStringList + GtkSignalListItemFactory (the
 * idiomatic virtualized path).
 * First-presented-frame: GdkFrameClock "after-paint" signal, connected
 * when the window is mapped.
 * Scroll-bench: a frame-clock tick callback advances the scrolled
 * window's vadjustment from wall-clock elapsed time; per-frame
 * timestamps come from "after-paint".
 */

#include <gtk/gtk.h>

#include <math.h>

#include "bench_common.h"

#define ROWS 10000
#define ROW_H 36
#define SPEED 1000.0 /* px/s */

static double duration_s = 6.0;

static gint64 t0_us;
static gboolean mode_startup = FALSE;
static gboolean mode_scroll = FALSE;
static gboolean reported = FALSE;

static gboolean first_frame_seen = FALSE;
static gint64 scroll_start_us = 0;
static GArray *frame_times = NULL; /* gint64, CLOCK_MONOTONIC us */
static GtkAdjustment *vadj = NULL;
static int count = 0;

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

static void on_count_clicked(GtkButton *btn, gpointer data) {
    (void)data;
    char buf[32];
    g_snprintf(buf, sizeof buf, "Count: %d", ++count);
    gtk_button_set_label(btn, buf);
}

static void on_scale_changed(GtkRange *range, gpointer data) {
    char buf[16];
    g_snprintf(buf, sizeof buf, "%d", (int)lround(gtk_range_get_value(range)));
    gtk_label_set_text(GTK_LABEL(data), buf);
}

static void factory_setup(GtkSignalListItemFactory *factory, GtkListItem *item,
                          gpointer data) {
    (void)factory;
    (void)data;
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    gtk_widget_set_size_request(box, -1, ROW_H);
    gtk_widget_set_margin_start(box, 8);
    GtkWidget *primary = gtk_label_new(NULL);
    gtk_widget_add_css_class(primary, "row-primary");
    GtkWidget *secondary = gtk_label_new(NULL);
    gtk_widget_add_css_class(secondary, "row-secondary");
    gtk_box_append(GTK_BOX(box), primary);
    gtk_box_append(GTK_BOX(box), secondary);
    gtk_list_item_set_child(item, box);
}

static void factory_bind(GtkSignalListItemFactory *factory, GtkListItem *item,
                         gpointer data) {
    (void)factory;
    (void)data;
    GtkWidget *box = gtk_list_item_get_child(item);
    GtkWidget *primary = gtk_widget_get_first_child(box);
    GtkWidget *secondary = gtk_widget_get_next_sibling(primary);
    guint pos = gtk_list_item_get_position(item);
    char buf[48];
    g_snprintf(buf, sizeof buf, "Item %u", pos);
    gtk_label_set_text(GTK_LABEL(primary), buf);
    g_snprintf(buf, sizeof buf, "subtitle %u", pos);
    gtk_label_set_text(GTK_LABEL(secondary), buf);
}

static void activate(GtkApplication *app, gpointer data) {
    (void)data;

    GtkCssProvider *css = gtk_css_provider_new();
    gtk_css_provider_load_from_string(
        css,
        "label.app-title { font-weight: bold; font-size: 18px; }"
        "label.row-primary { font-weight: bold; }"
        "label.row-secondary { color: #777777; }");
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
    GtkWidget *spacer = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_widget_set_hexpand(spacer, TRUE);
    GtkWidget *count_btn = gtk_button_new_with_label("Count: 0");
    g_signal_connect(count_btn, "clicked", G_CALLBACK(on_count_clicked), NULL);
    gtk_box_append(GTK_BOX(header), title);
    gtk_box_append(GTK_BOX(header), spacer);
    gtk_box_append(GTK_BOX(header), count_btn);

    /* List --------------------------------------------------------- */
    GtkStringList *strings = gtk_string_list_new(NULL);
    for (int i = 0; i < ROWS; i++) {
        char buf[16];
        g_snprintf(buf, sizeof buf, "%d", i);
        gtk_string_list_append(strings, buf);
    }
    GtkListItemFactory *factory = gtk_signal_list_item_factory_new();
    g_signal_connect(factory, "setup", G_CALLBACK(factory_setup), NULL);
    g_signal_connect(factory, "bind", G_CALLBACK(factory_bind), NULL);
    GtkWidget *list = gtk_list_view_new(
        GTK_SELECTION_MODEL(gtk_no_selection_new(G_LIST_MODEL(strings))),
        factory);
    GtkWidget *scrolled = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scrolled),
                                   GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scrolled), list);
    gtk_widget_set_vexpand(scrolled, TRUE);
    vadj = gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(scrolled));

    /* Footer ------------------------------------------------------- */
    GtkWidget *footer = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    gtk_widget_set_size_request(footer, -1, 56);
    gtk_widget_set_margin_start(footer, 8);
    gtk_widget_set_margin_end(footer, 8);
    gtk_widget_set_margin_top(footer, 8);
    gtk_widget_set_margin_bottom(footer, 8);
    GtkWidget *entry = gtk_entry_new();
    gtk_entry_set_placeholder_text(GTK_ENTRY(entry), "Type here...");
    gtk_widget_set_size_request(entry, 240, -1);
    GtkWidget *scale =
        gtk_scale_new_with_range(GTK_ORIENTATION_HORIZONTAL, 0, 100, 1);
    gtk_range_set_value(GTK_RANGE(scale), 50);
    gtk_widget_set_size_request(scale, 200, -1);
    GtkWidget *value_label = gtk_label_new("50");
    g_signal_connect(scale, "value-changed", G_CALLBACK(on_scale_changed),
                     value_label);
    gtk_box_append(GTK_BOX(footer), entry);
    gtk_box_append(GTK_BOX(footer), scale);
    gtk_box_append(GTK_BOX(footer), value_label);

    gtk_box_append(GTK_BOX(root), header);
    gtk_box_append(GTK_BOX(root), scrolled);
    gtk_box_append(GTK_BOX(root), footer);
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

    GtkApplication *app =
        gtk_application_new("org.lumen.benchcomp.gtk4", G_APPLICATION_NON_UNIQUE);
    g_signal_connect(app, "activate", G_CALLBACK(activate), NULL);
    /* Pass argc=1 so GApplication never sees our custom flags. */
    int status = g_application_run(G_APPLICATION(app), 1, argv);
    g_object_unref(app);
    return status;
}
