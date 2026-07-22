/* Bench forms app - GTK4 (C) variant: widget-dense settings page
 * (~40 controls in 6 GtkFrame groups; shared spec in the repo README).
 *
 * --interact drives, per cycle: a 40-step focus walk (real focus-chain
 * traversal via gtk_widget_child_focus(win, GTK_DIR_TAB_FORWARD)), then
 * a 20-step toggle-all pass (toggle 8 check buttons + 4 switches,
 * advance both radio groups - grouped GtkCheckButtons, GTK4's radio
 * primitive - through their 4 options; direct programmatic state
 * changes, same as the other frameworks). One step per 16 ms of wall
 * time, driven by a 4 ms g_timeout (independent of the frame clock so
 * a parked frame clock cannot stall the pass); the footer status label
 * changes every step so every step produces visible damage.
 * Frame timestamps: GdkFrameClock "after-paint" (frame handed to the
 * compositor), same as the other GTK apps. */

#include <gtk/gtk.h>

#include <math.h>

#include "bench_common.h"

#define STEP_S 0.016
#define SETTLE_S 0.5
#define STEPS_PER_CYCLE 60 /* 40 focus + 8 cb + 4 sw + 2x4 radio advances */

static gint64 t0_us;
static gboolean mode_startup = FALSE;
static gboolean mode_interact = FALSE;
static gboolean reported = FALSE;
static int cycles = 4;

static gboolean first_frame_seen = FALSE;
static gint64 first_frame_us = 0;
static gint64 started_us = 0;
static gint64 step_done = 0;
static GArray *frame_times = NULL; /* gint64, CLOCK_MONOTONIC us */

static GtkWidget *window_w = NULL;
static GtkWidget *status_label = NULL;
static GtkWidget *theme_label = NULL;
static GtkWidget *telemetry_label = NULL;
static GtkWidget *checks[8];
static GtkWidget *switches[4];
static GtkWidget *radio_a[4];
static GtkWidget *radio_b[4];
static int radio_a_idx = 0, radio_b_idx = 0;
static const char *radio_a_names[4] = {"System", "Light", "Dark",
                                       "High contrast"};
static const char *radio_b_names[4] = {"Off", "Crash reports only", "Basic",
                                       "Full"};

static void on_after_paint(GdkFrameClock *clock, gpointer data) {
    (void)clock;
    (void)data;
    gint64 now = g_get_monotonic_time();
    if (!first_frame_seen) {
        first_frame_seen = TRUE;
        first_frame_us = now;
        bench_print_first_frame();
        if (mode_startup) bench_print_startup_and_exit(t0_us, now);
        return;
    }
    if (mode_interact && !reported && started_us != 0)
        g_array_append_val(frame_times, now);
}

static void apply_step(gint64 step) {
    char buf[48];
    g_snprintf(buf, sizeof buf, "step %" G_GINT64_FORMAT, step);
    gtk_label_set_text(GTK_LABEL(status_label), buf);

    gint64 in_cycle = step % STEPS_PER_CYCLE;
    if (in_cycle < 40) {
        if (!gtk_widget_child_focus(window_w, GTK_DIR_TAB_FORWARD)) {
            /* Wrapped past the last stop: restart the walk. */
            gtk_widget_child_focus(window_w, GTK_DIR_TAB_FORWARD);
        }
        return;
    }
    gint64 t = in_cycle - 40;
    if (t <= 7) {
        GtkCheckButton *cb = GTK_CHECK_BUTTON(checks[t]);
        gtk_check_button_set_active(cb, !gtk_check_button_get_active(cb));
    } else if (t <= 11) {
        GtkSwitch *sw = GTK_SWITCH(switches[t - 8]);
        gtk_switch_set_active(sw, !gtk_switch_get_active(sw));
    } else if (t <= 15) {
        radio_a_idx = (radio_a_idx + 1) % 4;
        gtk_check_button_set_active(GTK_CHECK_BUTTON(radio_a[radio_a_idx]),
                                    TRUE);
        g_snprintf(buf, sizeof buf, "theme: %s", radio_a_names[radio_a_idx]);
        gtk_label_set_text(GTK_LABEL(theme_label), buf);
    } else {
        radio_b_idx = (radio_b_idx + 1) % 4;
        gtk_check_button_set_active(GTK_CHECK_BUTTON(radio_b[radio_b_idx]),
                                    TRUE);
        g_snprintf(buf, sizeof buf, "telemetry: %s", radio_b_names[radio_b_idx]);
        gtk_label_set_text(GTK_LABEL(telemetry_label), buf);
    }
}

static gboolean on_step_timeout(gpointer data) {
    (void)data;
    if (!mode_interact || reported || !first_frame_seen) return G_SOURCE_CONTINUE;
    gint64 now = g_get_monotonic_time();
    if ((double)(now - first_frame_us) / 1e6 < SETTLE_S) return G_SOURCE_CONTINUE;
    if (started_us == 0) {
        started_us = now;
        return G_SOURCE_CONTINUE;
    }
    gint64 total = (gint64)STEPS_PER_CYCLE * cycles;
    gint64 due = (gint64)(((double)(now - started_us) / 1e6) / STEP_S);
    if (due > total) due = total;
    while (step_done < due) {
        apply_step(step_done);
        step_done++;
    }
    if (step_done >= total) {
        /* Stay alive for the post-run memory sample. */
        bench_print_deltas_done(frame_times);
        reported = TRUE;
    }
    return G_SOURCE_CONTINUE;
}

static void on_map(GtkWidget *widget, gpointer data) {
    (void)data;
    GdkFrameClock *fc = gtk_widget_get_frame_clock(widget);
    g_signal_connect(fc, "after-paint", G_CALLBACK(on_after_paint), NULL);
}

static GtkWidget *labeled(const char *name, GtkWidget *control) {
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    GtkWidget *lab = gtk_label_new(name);
    gtk_widget_set_size_request(lab, 110, -1);
    gtk_label_set_xalign(GTK_LABEL(lab), 0.0);
    gtk_box_append(GTK_BOX(row), lab);
    gtk_box_append(GTK_BOX(row), control);
    return row;
}

static GtkWidget *make_entry(const char *ph, int width) {
    GtkWidget *e = gtk_entry_new();
    gtk_entry_set_placeholder_text(GTK_ENTRY(e), ph);
    gtk_widget_set_size_request(e, width, -1);
    return e;
}

static GtkWidget *make_scale(void) {
    GtkWidget *s =
        gtk_scale_new_with_range(GTK_ORIENTATION_HORIZONTAL, 0, 100, 1);
    gtk_range_set_value(GTK_RANGE(s), 50);
    gtk_widget_set_size_request(s, 200, -1);
    return s;
}

static GtkWidget *make_dropdown(const char *const *opts) {
    return gtk_drop_down_new_from_strings(opts);
}

static GtkWidget *make_group(const char *title, GtkWidget *content) {
    GtkWidget *frame = gtk_frame_new(title);
    gtk_frame_set_child(GTK_FRAME(frame), content);
    return frame;
}

static GtkWidget *vbox8(void) {
    GtkWidget *b = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
    gtk_widget_set_margin_start(b, 8);
    gtk_widget_set_margin_end(b, 8);
    gtk_widget_set_margin_top(b, 8);
    gtk_widget_set_margin_bottom(b, 8);
    return b;
}

static GtkWidget *check_row(GtkWidget *a, GtkWidget *b) {
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    gtk_box_append(GTK_BOX(row), a);
    gtk_box_append(GTK_BOX(row), b);
    return row;
}

static GtkWidget *button_row(const char *text) {
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_box_append(GTK_BOX(row), gtk_button_new_with_label(text));
    return row;
}

static GtkWidget *radio_col(GtkWidget **out, const char *const names[4]) {
    GtkWidget *col = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);
    GtkWidget *first = NULL;
    for (int i = 0; i < 4; i++) {
        GtkWidget *r = gtk_check_button_new_with_label(names[i]);
        if (!first) {
            first = r;
            gtk_check_button_set_active(GTK_CHECK_BUTTON(r), TRUE);
        } else {
            gtk_check_button_set_group(GTK_CHECK_BUTTON(r),
                                       GTK_CHECK_BUTTON(first));
        }
        out[i] = r;
        gtk_box_append(GTK_BOX(col), r);
    }
    return col;
}

static void activate(GtkApplication *app, gpointer data) {
    (void)data;

    GtkCssProvider *css = gtk_css_provider_new();
    gtk_css_provider_load_from_string(
        css,
        "label.app-title { font-weight: bold; font-size: 18px; }"
        "label.footer-status { color: #777777; }");
    gtk_style_context_add_provider_for_display(
        gdk_display_get_default(), GTK_STYLE_PROVIDER(css),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);

    GtkWidget *win = gtk_application_window_new(app);
    window_w = win;
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

    /* Form --------------------------------------------------------- */
    GtkWidget *form = gtk_box_new(GTK_ORIENTATION_VERTICAL, 12);
    gtk_widget_set_margin_start(form, 8);
    gtk_widget_set_margin_end(form, 8);
    gtk_widget_set_margin_top(form, 8);
    gtk_widget_set_margin_bottom(form, 8);

    int ci = 0, si = 0;

    /* Account */
    {
        GtkWidget *b = vbox8();
        gtk_box_append(GTK_BOX(b), labeled("Username:", make_entry("Username", 220)));
        gtk_box_append(GTK_BOX(b), labeled("Email:", make_entry("Email", 220)));
        checks[ci] = gtk_check_button_new_with_label("Remember me");
        checks[ci + 1] = gtk_check_button_new_with_label("Subscribe to newsletter");
        gtk_box_append(GTK_BOX(b), check_row(checks[ci], checks[ci + 1]));
        ci += 2;
        gtk_box_append(GTK_BOX(b), button_row("Sign out"));
        gtk_box_append(GTK_BOX(form), make_group("Account", b));
    }
    /* Appearance */
    {
        static const char *density[] = {"Compact", "Cozy", "Normal",
                                        "Comfortable", "Spacious", NULL};
        GtkWidget *b = vbox8();
        gtk_box_append(GTK_BOX(b), labeled("Theme:", radio_col(radio_a, radio_a_names)));
        gtk_box_append(GTK_BOX(b), labeled("Font size:", make_scale()));
        gtk_box_append(GTK_BOX(b), labeled("Density:", make_dropdown(density)));
        switches[si] = gtk_switch_new();
        gtk_widget_set_halign(switches[si], GTK_ALIGN_START);
        gtk_box_append(GTK_BOX(b), labeled("Animations:", switches[si]));
        si++;
        gtk_box_append(GTK_BOX(form), make_group("Appearance", b));
    }
    /* Network */
    {
        static const char *protocol[] = {"Auto", "HTTP/1.1", "HTTP/2",
                                         "HTTP/3", "SOCKS5", NULL};
        GtkWidget *b = vbox8();
        gtk_box_append(GTK_BOX(b), labeled("Proxy host:", make_entry("proxy.example.com", 220)));
        gtk_box_append(GTK_BOX(b), labeled("Proxy port:", make_entry("8080", 100)));
        checks[ci] = gtk_check_button_new_with_label("Use proxy");
        checks[ci + 1] = gtk_check_button_new_with_label("Verify TLS certificates");
        gtk_box_append(GTK_BOX(b), check_row(checks[ci], checks[ci + 1]));
        ci += 2;
        gtk_box_append(GTK_BOX(b), labeled("Timeout:", make_scale()));
        gtk_box_append(GTK_BOX(b), labeled("Protocol:", make_dropdown(protocol)));
        gtk_box_append(GTK_BOX(b), button_row("Test connection"));
        gtk_box_append(GTK_BOX(form), make_group("Network", b));
    }
    /* Editor */
    {
        static const char *endings[] = {"Auto", "LF", "CRLF", "CR",
                                        "Keep mixed", NULL};
        GtkWidget *b = vbox8();
        gtk_box_append(GTK_BOX(b), labeled("Font family:", make_entry("monospace", 220)));
        gtk_box_append(GTK_BOX(b), labeled("Tab width:", make_entry("4", 100)));
        checks[ci] = gtk_check_button_new_with_label("Word wrap");
        checks[ci + 1] = gtk_check_button_new_with_label("Line numbers");
        gtk_box_append(GTK_BOX(b), check_row(checks[ci], checks[ci + 1]));
        ci += 2;
        gtk_box_append(GTK_BOX(b), labeled("Line endings:", make_dropdown(endings)));
        gtk_box_append(GTK_BOX(b), labeled("Rulers:", make_scale()));
        switches[si] = gtk_switch_new();
        gtk_widget_set_halign(switches[si], GTK_ALIGN_START);
        gtk_box_append(GTK_BOX(b), labeled("Autosave:", switches[si]));
        si++;
        gtk_box_append(GTK_BOX(form), make_group("Editor", b));
    }
    /* Privacy */
    {
        GtkWidget *b = vbox8();
        gtk_box_append(GTK_BOX(b), labeled("Telemetry:", radio_col(radio_b, radio_b_names)));
        checks[ci] = gtk_check_button_new_with_label("Upload crash reports");
        checks[ci + 1] = gtk_check_button_new_with_label("Share usage statistics");
        gtk_box_append(GTK_BOX(b), check_row(checks[ci], checks[ci + 1]));
        ci += 2;
        switches[si] = gtk_switch_new();
        gtk_widget_set_halign(switches[si], GTK_ALIGN_START);
        gtk_box_append(GTK_BOX(b), labeled("Do not track:", switches[si]));
        si++;
        gtk_box_append(GTK_BOX(b), button_row("Clear data"));
        gtk_box_append(GTK_BOX(form), make_group("Privacy", b));
    }
    /* Advanced */
    {
        static const char *levels[] = {"Error", "Warn", "Info", "Debug",
                                       "Trace", NULL};
        GtkWidget *b = vbox8();
        gtk_box_append(GTK_BOX(b), labeled("Config path:", make_entry("~/.config/bench", 220)));
        gtk_box_append(GTK_BOX(b), labeled("Log filter:", make_entry("info", 220)));
        gtk_box_append(GTK_BOX(b), labeled("Log level:", make_dropdown(levels)));
        gtk_box_append(GTK_BOX(b), labeled("Cache size:", make_scale()));
        switches[si] = gtk_switch_new();
        gtk_widget_set_halign(switches[si], GTK_ALIGN_START);
        gtk_box_append(GTK_BOX(b), labeled("Experimental:", switches[si]));
        si++;
        gtk_box_append(GTK_BOX(b), button_row("Reset all"));
        gtk_box_append(GTK_BOX(form), make_group("Advanced", b));
    }

    GtkWidget *scrolled = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scrolled),
                                   GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scrolled), form);
    gtk_widget_set_vexpand(scrolled, TRUE);

    /* Footer ------------------------------------------------------- */
    GtkWidget *footer = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    gtk_widget_set_size_request(footer, -1, 32);
    gtk_widget_set_margin_start(footer, 8);
    gtk_widget_set_margin_end(footer, 8);
    gtk_widget_set_margin_top(footer, 4);
    gtk_widget_set_margin_bottom(footer, 4);
    status_label = gtk_label_new("idle");
    theme_label = gtk_label_new("theme: System");
    telemetry_label = gtk_label_new("telemetry: Off");
    gtk_widget_add_css_class(status_label, "footer-status");
    gtk_widget_add_css_class(theme_label, "footer-status");
    gtk_widget_add_css_class(telemetry_label, "footer-status");
    gtk_box_append(GTK_BOX(footer), status_label);
    gtk_box_append(GTK_BOX(footer), theme_label);
    gtk_box_append(GTK_BOX(footer), telemetry_label);

    gtk_box_append(GTK_BOX(root), header);
    gtk_box_append(GTK_BOX(root), scrolled);
    gtk_box_append(GTK_BOX(root), footer);
    gtk_window_set_child(GTK_WINDOW(win), root);

    g_signal_connect(win, "map", G_CALLBACK(on_map), NULL);
    if (mode_interact) g_timeout_add(4, on_step_timeout, NULL);

    gtk_window_present(GTK_WINDOW(win));
}

int main(int argc, char **argv) {
    t0_us = g_get_monotonic_time();
    BenchMode mode = bench_parse_mode(argc, argv);
    mode_startup = (mode == BENCH_MODE_STARTUP);
    mode_interact = (mode == BENCH_MODE_INTERACT);
    cycles = bench_interact_cycles();
    frame_times = g_array_sized_new(FALSE, FALSE, sizeof(gint64), 4096);

    GtkApplication *app = gtk_application_new("org.lumen.benchcomp.gtk4.forms",
                                              G_APPLICATION_NON_UNIQUE);
    g_signal_connect(app, "activate", G_CALLBACK(activate), NULL);
    /* Pass argc=1 so GApplication never sees our custom flags. */
    int status = g_application_run(G_APPLICATION(app), 1, argv);
    g_object_unref(app);
    return status;
}
