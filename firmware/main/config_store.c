#include "config_store.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "config_store";
static const char *NS = "edge";
static const char *KEY = "devcfg";

static devcfg_t s_cfg;
static SemaphoreHandle_t s_lock;

esp_err_t config_store_init(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    if (err != ESP_OK) {
        return err;
    }
    s_lock = xSemaphoreCreateMutex();
    devcfg_defaults(&s_cfg);

    nvs_handle_t h;
    if (nvs_open(NS, NVS_READONLY, &h) == ESP_OK) {
        devcfg_t stored;
        size_t size = sizeof stored;
        esp_err_t gerr = nvs_get_blob(h, KEY, &stored, &size);
        if (gerr == ESP_OK && size == sizeof stored && devcfg_valid(&stored)) {
            s_cfg = stored;
            ESP_LOGI(TAG, "loaded config from NVS");
        } else if (gerr == ESP_OK) {
            ESP_LOGW(TAG, "stored config invalid, using defaults");
        }
        nvs_close(h);
    }
    return ESP_OK;
}

void config_store_get(devcfg_t *out)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    *out = s_cfg;
    xSemaphoreGive(s_lock);
}

esp_err_t config_store_set(const devcfg_t *c)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool changed = !devcfg_equal(&s_cfg, c);
    s_cfg = *c;
    xSemaphoreGive(s_lock);
    if (!changed) {
        return ESP_OK; /* avoid flash wear on redelivered retained config */
    }

    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    if (err == ESP_OK) {
        err = nvs_set_blob(h, KEY, c, sizeof *c);
        if (err == ESP_OK) {
            err = nvs_commit(h);
        }
        nvs_close(h);
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "saving config failed: %s", esp_err_to_name(err));
    }
    return err;
}
