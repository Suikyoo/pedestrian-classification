#pragma once
#include <stdbool.h>

#include "esp_err.h"

/* Capture loop, every interval_ms: detect pedestrians, run the dwell rule, play
 * the alert and queue an event when it fires, and, while streaming, also
 * publish the frame to master. detect_ready is the detect_init() result: false
 * keeps stream_detect_ok() false until a detection succeeds. */
esp_err_t stream_start(bool detect_ready);

/* False after repeated detection failures (no model, decode errors). */
bool stream_detect_ok(void);
