#include "core/devcfg.h"

#include <string.h>

#include "cJSON.h"

static const char *const FRAME_NAMES[DEVCFG_FRAME_COUNT] = {
    "QVGA", "VGA", "SVGA", "XGA", "HD", "SXGA", "UXGA",
};

void devcfg_defaults(devcfg_t *c)
{
    c->interval_ms = 1000;
    c->jpeg_quality = 12;
    c->frame_size = DEVCFG_FRAME_VGA;
    c->volume = 80;
    c->streaming = false;
    c->threshold = 0.6f;
    c->dwell_s = 5.0f;
    c->max_gap_s = 3.0f;
    c->cooldown_s = 30.0f;
    c->rotation = 0;
}

bool devcfg_equal(const devcfg_t *a, const devcfg_t *b)
{
    return a->interval_ms == b->interval_ms && a->jpeg_quality == b->jpeg_quality &&
           a->frame_size == b->frame_size && a->volume == b->volume &&
           a->streaming == b->streaming && a->threshold == b->threshold &&
           a->dwell_s == b->dwell_s && a->max_gap_s == b->max_gap_s &&
           a->cooldown_s == b->cooldown_s && a->rotation == b->rotation;
}

const char *devcfg_frame_name(devcfg_frame_t f)
{
    return (unsigned)f < DEVCFG_FRAME_COUNT ? FRAME_NAMES[f] : NULL;
}

bool devcfg_frame_from_name(const char *name, devcfg_frame_t *out)
{
    for (int i = 0; i < DEVCFG_FRAME_COUNT; i++) {
        if (strcmp(name, FRAME_NAMES[i]) == 0) {
            *out = (devcfg_frame_t)i;
            return true;
        }
    }
    return false;
}

/* Reads an optional integer field. Returns false only if present and invalid. */
static bool read_int(const cJSON *root, const char *key, long lo, long hi, bool *present, long *out)
{
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(root, key);
    *present = item != NULL;
    if (item == NULL) {
        return true;
    }
    if (!cJSON_IsNumber(item)) {
        return false;
    }
    double v = item->valuedouble;
    if (v < (double)lo || v > (double)hi || v != (double)(long)v) {
        return false;
    }
    *out = (long)v;
    return true;
}

/* Reads an optional number field. Returns false only if present and invalid. */
static bool read_float(const cJSON *root, const char *key, double lo, double hi, bool *present, float *out)
{
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(root, key);
    *present = item != NULL;
    if (item == NULL) {
        return true;
    }
    if (!cJSON_IsNumber(item)) {
        return false;
    }
    double v = item->valuedouble;
    if (!(v >= lo && v <= hi)) { /* also rejects NaN */
        return false;
    }
    *out = (float)v;
    return true;
}

bool devcfg_apply_json(devcfg_t *c, const char *json, size_t len)
{
    cJSON *root = cJSON_ParseWithLength(json, len);
    if (!cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return false;
    }

    devcfg_t next = *c;
    bool ok = true;
    bool present;
    long v = 0;

    ok = ok && read_int(root, "interval_ms", 100, 3600000, &present, &v);
    if (ok && present) {
        next.interval_ms = (uint32_t)v;
    }
    ok = ok && read_int(root, "jpeg_quality", 0, 63, &present, &v);
    if (ok && present) {
        next.jpeg_quality = (uint8_t)v;
    }
    ok = ok && read_int(root, "volume", 0, 100, &present, &v);
    if (ok && present) {
        next.volume = (uint8_t)v;
    }
    /* Only 0 and 180: the sensor can flip, not turn by 90 degrees. */
    ok = ok && read_int(root, "rotation", 0, 180, &present, &v) && (!present || v == 0 || v == 180);
    if (ok && present) {
        next.rotation = (uint16_t)v;
    }
    float f = 0.0f;
    ok = ok && read_float(root, "threshold", 0.05, 0.99, &present, &f);
    if (ok && present) {
        next.threshold = f;
    }
    ok = ok && read_float(root, "dwell_s", 0.0, 600.0, &present, &f);
    if (ok && present) {
        next.dwell_s = f;
    }
    ok = ok && read_float(root, "max_gap_s", 0.5, 60.0, &present, &f);
    if (ok && present) {
        next.max_gap_s = f;
    }
    ok = ok && read_float(root, "cooldown_s", 0.0, 3600.0, &present, &f);
    if (ok && present) {
        next.cooldown_s = f;
    }
    const cJSON *fs = cJSON_GetObjectItemCaseSensitive(root, "frame_size");
    if (ok && fs != NULL) {
        ok = cJSON_IsString(fs) && devcfg_frame_from_name(fs->valuestring, &next.frame_size);
    }

    cJSON_Delete(root);
    if (ok) {
        *c = next;
    }
    return ok;
}

bool devcfg_valid(const devcfg_t *c)
{
    return c->interval_ms >= 100 && c->interval_ms <= 3600000 &&
           c->jpeg_quality <= 63 &&
           (unsigned)c->frame_size < DEVCFG_FRAME_COUNT &&
           c->volume <= 100 &&
           c->threshold >= 0.05f && c->threshold <= 0.99f &&
           c->dwell_s >= 0.0f && c->dwell_s <= 600.0f &&
           c->max_gap_s >= 0.5f && c->max_gap_s <= 60.0f &&
           c->cooldown_s >= 0.0f && c->cooldown_s <= 3600.0f &&
           (c->rotation == 0 || c->rotation == 180);
}
