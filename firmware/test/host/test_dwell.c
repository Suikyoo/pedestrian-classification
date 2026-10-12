#include "core/dwell.h"
#include "minitest.h"

#define POS 0.9f
#define NEG 0.1f

static const dwell_params_t P = {.threshold = 0.6f, .dwell_ms = 5000, .max_gap_ms = 3000, .cooldown_ms = 30000};

static int s_alerts;
static int64_t s_at[8];
static dwell_alert_t s_last;

static void start(dwell_t *d)
{
    dwell_init(d);
    s_alerts = 0;
}

/* One frame at `sec` seconds on the monotonic clock. */
static void frame(dwell_t *d, int64_t sec, float score)
{
    dwell_alert_t a;
    if (dwell_update(d, &P, sec * 1000, score, &a)) {
        if (s_alerts < 8) {
            s_at[s_alerts] = a.alert_ms;
        }
        s_alerts++;
        s_last = a;
    }
}

/* One frame per second for seconds [from, to). */
static void run(dwell_t *d, int64_t from, int64_t to, float score)
{
    for (int64_t s = from; s < to; s++) {
        frame(d, s, score);
    }
}

static void test_alert_when_dwell_reached(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 6, POS);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_at[0], 5000);
}

static void test_no_alert_before_dwell(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 5, POS);
    CHECK_INT(s_alerts, 0);
}

static void test_score_equal_to_threshold_is_positive(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 6, 0.6f);
    CHECK_INT(s_alerts, 1);
}

static void test_gap_longer_than_max_gap_resets(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 3, POS);
    run(&d, 6, 12, POS);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_at[0], 11000);
}

static void test_single_negative_frame_does_not_reset(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 3, POS);
    frame(&d, 3, NEG);
    run(&d, 4, 6, POS);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_at[0], 5000);
}

static void test_failed_detection_counts_as_negative(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 3, POS);
    frame(&d, 3, -1.0f);
    run(&d, 4, 6, POS);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_at[0], 5000);
}

static void test_negatives_longer_than_max_gap_reset(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 2, POS);
    run(&d, 2, 6, NEG);
    run(&d, 6, 12, POS);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_at[0], 11000);
}

static void test_cooldown_suppresses_repeats(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 41, POS);
    CHECK_INT(s_alerts, 2);
    CHECK_INT(s_at[0], 5000);
    CHECK_INT(s_at[1], 35000);
}

static void test_alert_carries_first_seen_and_max_score(void)
{
    dwell_t d;
    start(&d);
    frame(&d, 10, 0.7f);
    frame(&d, 11, 0.95f);
    frame(&d, 12, 0.8f);
    run(&d, 13, 16, 0.7f);
    CHECK_INT(s_alerts, 1);
    CHECK_INT(s_last.first_seen_ms, 10000);
    CHECK_INT(s_last.alert_ms, 15000);
    CHECK(s_last.max_score == 0.95f);
}

static void test_current_dwell(void)
{
    dwell_t d;
    start(&d);
    CHECK_INT(dwell_current_ms(&d), 0);
    run(&d, 0, 3, POS);
    CHECK_INT(dwell_current_ms(&d), 2000);
    frame(&d, 3, NEG); /* run continues inside the gap */
    CHECK_INT(dwell_current_ms(&d), 2000);
    frame(&d, 7, POS); /* gap 5 s > 3 s: new run */
    CHECK_INT(dwell_current_ms(&d), 0);
    frame(&d, 8, POS);
    CHECK_INT(dwell_current_ms(&d), 1000);
}

static void test_param_change_keeps_state(void)
{
    dwell_t d;
    start(&d);
    run(&d, 0, 3, POS);
    dwell_params_t shorter = P;
    shorter.dwell_ms = 3000;
    dwell_alert_t a;
    CHECK(dwell_update(&d, &shorter, 3000, POS, &a));
    CHECK_INT(a.first_seen_ms, 0);
}

static void test_params_from_cfg(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    dwell_params_t p;
    dwell_params_from_cfg(&p, &c);
    CHECK(p.threshold == 0.6f);
    CHECK_INT(p.dwell_ms, 5000);
    CHECK_INT(p.max_gap_ms, 3000);
    CHECK_INT(p.cooldown_ms, 30000);
    c.dwell_s = 0.25f;
    dwell_params_from_cfg(&p, &c);
    CHECK_INT(p.dwell_ms, 250);
}

void test_dwell(void)
{
    test_alert_when_dwell_reached();
    test_no_alert_before_dwell();
    test_score_equal_to_threshold_is_positive();
    test_gap_longer_than_max_gap_resets();
    test_single_negative_frame_does_not_reset();
    test_failed_detection_counts_as_negative();
    test_negatives_longer_than_max_gap_reset();
    test_cooldown_suppresses_repeats();
    test_alert_carries_first_seen_and_max_score();
    test_current_dwell();
    test_param_change_keeps_state();
    test_params_from_cfg();
}
