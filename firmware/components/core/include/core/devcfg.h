#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    DEVCFG_FRAME_QVGA,
    DEVCFG_FRAME_VGA,
    DEVCFG_FRAME_SVGA,
    DEVCFG_FRAME_XGA,
    DEVCFG_FRAME_HD,
    DEVCFG_FRAME_SXGA,
    DEVCFG_FRAME_UXGA,
    DEVCFG_FRAME_COUNT,
} devcfg_frame_t;

/* Runtime config. Persisted in NVS; updated by {id}/config and start/stop. */
typedef struct {
    uint32_t interval_ms;     /* 100..3600000 */
    uint8_t jpeg_quality;     /* 0..63, lower = better */
    devcfg_frame_t frame_size;
    uint8_t volume;           /* 0..100 */
    bool streaming;
} devcfg_t;

void devcfg_defaults(devcfg_t *c);

/* Apply a {id}/config JSON object. Missing fields keep their value, unknown
 * fields are ignored. If any known field is invalid, or the JSON is not an
 * object, nothing changes and false is returned. `json` need not be
 * NUL-terminated. */
bool devcfg_apply_json(devcfg_t *c, const char *json, size_t len);

/* True if every field is within the protocol ranges. */
bool devcfg_valid(const devcfg_t *c);

bool devcfg_equal(const devcfg_t *a, const devcfg_t *b);

const char *devcfg_frame_name(devcfg_frame_t f);
bool devcfg_frame_from_name(const char *name, devcfg_frame_t *out);
