/* Bench hello app - GTK4 (C) variant: minimal static window, one
 * "Hello" label + one button. Isolates the startup floor and baseline
 * memory.
 * First-presented-frame: GdkFrameClock "after-paint", connected on map
 * - same proxy as the other GTK apps. */

#include <gtk/gtk.h>

#include "bench_common.h"

static gint64 t0_us;
static gboolean mode_startup = FALSE;
static gboolean first_frame_seen = FALSE;

static void on_after_paint(GdkFrameClock *clock, gpointer data) {
    (void)clock;
    (void)data;
    if (first_frame_seen) return;
    first_frame_seen = TRUE;
    gint64 now = g_get_monotonic_time();
    bench_print_first_frame();
    if (mode_startup) bench_print_startup_and_exit(t0_us, now);
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
        css, "label.hello-title { font-weight: bold; font-size: 18px; }");
    gtk_style_context_add_provider_for_display(
        gdk_display_get_default(), GTK_STYLE_PROVIDER(css),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);

    GtkWidget *win = gtk_application_window_new(app);
    gtk_window_set_title(GTK_WINDOW(win), "Bench");
    gtk_window_set_default_size(GTK_WINDOW(win), 800, 600);

    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12);
    gtk_widget_set_halign(box, GTK_ALIGN_CENTER);
    gtk_widget_set_valign(box, GTK_ALIGN_CENTER);
    GtkWidget *label = gtk_label_new("Hello");
    gtk_widget_add_css_class(label, "hello-title");
    GtkWidget *btn = gtk_button_new_with_label("Press");
    gtk_box_append(GTK_BOX(box), label);
    gtk_box_append(GTK_BOX(box), btn);
    gtk_window_set_child(GTK_WINDOW(win), box);

    g_signal_connect(win, "map", G_CALLBACK(on_map), NULL);
    gtk_window_present(GTK_WINDOW(win));
}

int main(int argc, char **argv) {
    t0_us = g_get_monotonic_time();
    mode_startup = (bench_parse_mode(argc, argv) == BENCH_MODE_STARTUP);

    GtkApplication *app = gtk_application_new("org.lumen.benchcomp.gtk4.hello",
                                              G_APPLICATION_NON_UNIQUE);
    g_signal_connect(app, "activate", G_CALLBACK(activate), NULL);
    /* Pass argc=1 so GApplication never sees our custom flags. */
    int status = g_application_run(G_APPLICATION(app), 1, argv);
    g_object_unref(app);
    return status;
}
