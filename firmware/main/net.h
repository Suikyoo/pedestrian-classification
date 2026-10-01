#pragma once
#include <stdbool.h>

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

/* Network link, independent of the backend (Wi-Fi now, LTE later).
 * The backend reconnects on its own with core/backoff.h delays. */
esp_err_t net_start(void);                   /* start the link; returns at once */
bool net_wait_connected(TickType_t timeout); /* true once an IP address is held */
int net_rssi(void);                          /* dBm; 0 if unknown */
