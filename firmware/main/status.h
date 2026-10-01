#pragma once
#include "esp_err.h"

/* Publishes {id}/status (QoS 1, retained) every 60 s and on request. */
esp_err_t status_start(void);
void status_request(void); /* safe from any task; never blocks */
