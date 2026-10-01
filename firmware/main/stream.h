#pragma once
#include "esp_err.h"

/* Capture loop: while streaming and MQTT is connected, publish one frame per interval_ms. */
esp_err_t stream_start(void);
