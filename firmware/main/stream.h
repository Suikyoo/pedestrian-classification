#pragma once
#include <stdbool.h>

#include "esp_err.h"

/* Capture loop, every interval_ms: detect pedestrians, run the dwell rule, play
 * the alert and queue an event when it fires, and, while streaming, also
 * publish the frame to master. */
esp_err_t stream_start(void);

/* False after repeated detection failures (no model, decode errors). */
bool stream_detect_ok(void);
