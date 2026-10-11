#pragma once
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Loads the INT8 pedestrian model from the "pedestrian_det" partition. On
 * failure it logs why and returns an error; detect_score() then always fails. */
esp_err_t detect_init(void);

/* Highest pedestrian score (0..1) in a JPEG frame, 0 when nobody is found, or a
 * negative value when the frame cannot be decoded or no model is loaded.
 * Not thread-safe: call from one task only. */
float detect_score(const uint8_t *jpeg, size_t len);

#ifdef __cplusplus
}
#endif
