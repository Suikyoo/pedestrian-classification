#pragma once
#include <stdbool.h>
#include <stddef.h>

#include "core/proto.h"
#include "esp_err.h"

typedef struct {
    /* Called on the MQTT task for {id}/alert, {id}/cmd, {id}/config.
     * `data` is not NUL-terminated. Must not block. */
    void (*on_message)(proto_kind_t kind, const char *data, size_t len);
    /* Called on the MQTT task after every (re)connect. Must not block. */
    void (*on_connected)(void);
} mqtt_link_handlers_t;

esp_err_t mqtt_link_start(const char *device_id, const mqtt_link_handlers_t *handlers);
bool mqtt_link_connected(void);
/* Publish to {id}/{kind}. Returns the message id, or -1 if not connected or failed. */
int mqtt_link_publish(const char *kind, const void *data, size_t len, int qos, bool retain);
