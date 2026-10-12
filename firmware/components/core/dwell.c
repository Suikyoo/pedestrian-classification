#include "core/dwell.h"

static void end_run(dwell_t *d)
{
    d->first_seen_ms = -1;
    d->last_seen_ms = -1;
    d->max_score = 0.0f;
}

void dwell_init(dwell_t *d)
{
    end_run(d);
    d->last_alert_ms = -1;
}

static uint32_t to_ms(float s)
{
    return (uint32_t)(s * 1000.0f + 0.5f);
}

void dwell_params_from_cfg(dwell_params_t *p, const devcfg_t *c)
{
    p->threshold = c->threshold;
    p->dwell_ms = to_ms(c->dwell_s);
    p->max_gap_ms = to_ms(c->max_gap_s);
    p->cooldown_ms = to_ms(c->cooldown_s);
}

bool dwell_update(dwell_t *d, const dwell_params_t *p, int64_t now_ms, float score, dwell_alert_t *out)
{
    if (d->last_seen_ms >= 0 && now_ms - d->last_seen_ms > (int64_t)p->max_gap_ms) {
        end_run(d);
    }
    if (!(score >= p->threshold)) { /* negative, failed (< 0), or NaN */
        return false;
    }
    if (d->first_seen_ms < 0) {
        d->first_seen_ms = now_ms;
    }
    d->last_seen_ms = now_ms;
    if (score > d->max_score) {
        d->max_score = score;
    }
    if (now_ms - d->first_seen_ms < (int64_t)p->dwell_ms) {
        return false;
    }
    if (d->last_alert_ms >= 0 && now_ms - d->last_alert_ms < (int64_t)p->cooldown_ms) {
        return false;
    }
    d->last_alert_ms = now_ms;
    out->first_seen_ms = d->first_seen_ms;
    out->alert_ms = now_ms;
    out->max_score = d->max_score;
    return true;
}

uint32_t dwell_current_ms(const dwell_t *d)
{
    if (d->first_seen_ms < 0 || d->last_seen_ms < 0) {
        return 0;
    }
    return (uint32_t)(d->last_seen_ms - d->first_seen_ms);
}
