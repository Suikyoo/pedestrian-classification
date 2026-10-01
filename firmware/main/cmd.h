#pragma once
#include <stddef.h>

#include "core/proto.h"
#include "esp_err.h"

esp_err_t cmd_start(void);
/* Queue an incoming message for the command task. Safe to call from the MQTT
 * task; never blocks. Matches mqtt_link_handlers_t.on_message. */
void cmd_submit(proto_kind_t kind, const char *data, size_t len);
