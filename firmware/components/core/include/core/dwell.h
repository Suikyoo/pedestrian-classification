#pragma once
#include <stdbool.h>
#include <stdint.h>

#include "core/devcfg.h"

/* Dwell rule for one device: alert when a pedestrian is seen continuously for
 * dwell_ms. A positive frame has score >= threshold; a failed detection
 * (score < 0) is negative. Negative frames do not end a run by themselves: the
 * run ends when no positive frame was seen for longer than max_gap_ms. */

typedef struct {
    float threshold;
    uint32_t dwell_ms;
    uint32_t max_gap_ms;
    uint32_t cooldown_ms;
} dwell_params_t;

typedef struct {
    int64_t first_seen_ms; /* -1 = no run */
    int64_t last_seen_ms;  /* -1 = no run */
    int64_t last_alert_ms; /* -1 = never */
    float max_score;
} dwell_t;

typedef struct {
    int64_t first_seen_ms;
    int64_t alert_ms;
    float max_score;
} dwell_alert_t;

void dwell_init(dwell_t *d);
void dwell_params_from_cfg(dwell_params_t *p, const devcfg_t *c);

/* Feed one frame. now_ms is a monotonic clock and must not decrease. Returns
 * true and fills *out when an alert fires. Parameters may change between calls
 * without resetting the state. */
bool dwell_update(dwell_t *d, const dwell_params_t *p, int64_t now_ms, float score, dwell_alert_t *out);

/* Milliseconds the current run has lasted (0 if there is none). */
uint32_t dwell_current_ms(const dwell_t *d);
