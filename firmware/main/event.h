#pragma once
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

/* Publishes {id}/event (QoS 0) for alert candidates. Events raised while
 * offline wait in a queue of 4; when it is full the oldest waiting event is
 * dropped. An event leaves the queue once it is queued into the MQTT
 * outbox; there is no broker acknowledgement. */
esp_err_t event_start(void);

/* Queue a candidate event: max_score = score, alert_ms = first_seen_ms =
 * capture_ms, dwell_s = 0 (the host applies dwell). Copies the JPEG.
 * capture_ms is the frame's Unix ms (0 if the clock is not synced). Never
 * waits for the network. */
void event_raise(float score, uint64_t capture_ms, const uint8_t *jpeg, size_t len);
