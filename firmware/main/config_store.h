#pragma once
#include "core/devcfg.h"
#include "esp_err.h"

/* Runtime config kept in RAM and NVS. Thread-safe. */
esp_err_t config_store_init(void);
void config_store_get(devcfg_t *out);
esp_err_t config_store_set(const devcfg_t *c);
