#pragma once
#include <stddef.h>
#include <stdint.h>

#include "core/dwell.h"
#include "esp_err.h"

/* Publishes {id}/event (QoS 1) for local alerts. Events raised while offline
 * wait in a queue of 4; when it is full the oldest waiting event is dropped.
 * An event leaves the queue only after the broker acknowledges it (PUBACK);
 * unacknowledged events are sent again, so master may see duplicates. */
esp_err_t event_start(void);

/* Wire to mqtt_link_handlers_t.on_published. Safe from the MQTT task; never blocks long. */
void event_on_published(int msg_id);

/* Queue an event for `a`. Copies the JPEG. capture_ms is the alerting frame's
 * Unix ms (0 if the clock is not synced). Never waits for the network. */
void event_raise(const dwell_alert_t *a, uint64_t capture_ms, const uint8_t *jpeg, size_t len);
