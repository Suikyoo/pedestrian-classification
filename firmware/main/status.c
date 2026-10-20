#include "status.h"

#include <math.h>

#include "board.h"
#include "config_store.h"
#include "core/msg.h"
#include "driver/temperature_sensor.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mqtt_link.h"
#include "net.h"
#include "sdkconfig.h"
#include "stream.h"

static const char *TAG = "status";
#define STATUS_PERIOD_MS 60000

static TaskHandle_t s_task;
static temperature_sensor_handle_t s_tsens;

/* Starts the on-chip temperature sensor. Status reports temp_c: null if this fails. */
static void tsens_start(void)
{
    temperature_sensor_config_t cfg = TEMPERATURE_SENSOR_CONFIG_DEFAULT(20, 100);
    if (temperature_sensor_install(&cfg, &s_tsens) != ESP_OK) {
        s_tsens = NULL;
    } else if (temperature_sensor_enable(s_tsens) != ESP_OK) {
        temperature_sensor_uninstall(s_tsens);
        s_tsens = NULL;
    }
    if (s_tsens == NULL) {
        ESP_LOGW(TAG, "temperature sensor unavailable");
    }
}

static float chip_temp_c(void)
{
    float t;
    if (s_tsens == NULL || temperature_sensor_get_celsius(s_tsens, &t) != ESP_OK) {
        return NAN;
    }
    return t;
}

void status_request(void)
{
    if (s_task != NULL) {
        xTaskNotifyGive(s_task);
    }
}

static void publish_status(void)
{
    devcfg_t cfg;
    config_store_get(&cfg);
    msg_status_t s = {
        .rssi = net_rssi(),
        .battery_mv = board_battery_mv(),
        .uptime_s = (uint32_t)(esp_timer_get_time() / 1000000),
        .streaming = cfg.streaming,
        .fw = CONFIG_FW_VERSION,
        .detect_ok = stream_detect_ok(),
        .threshold = cfg.threshold,
        .dwell_s = cfg.dwell_s,
        .max_gap_s = cfg.max_gap_s,
        .cooldown_s = cfg.cooldown_s,
        .temp_c = chip_temp_c(),
    };
    char buf[256];
    int n = msg_format_status(buf, sizeof buf, &s);
    if (n < 0) {
        ESP_LOGE(TAG, "status does not fit buffer");
        return;
    }
    if (mqtt_link_publish("status", buf, (size_t)n, 1, true) < 0) {
        ESP_LOGD(TAG, "not connected, status skipped");
    }
}

static void status_task(void *arg)
{
    for (;;) {
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(STATUS_PERIOD_MS));
        publish_status();
    }
}

esp_err_t status_start(void)
{
    tsens_start();
    return xTaskCreate(status_task, "status", 4096, NULL, 3, &s_task) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
