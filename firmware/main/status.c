#include "status.h"

#include "board.h"
#include "config_store.h"
#include "core/msg.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mqtt_link.h"
#include "net.h"
#include "sdkconfig.h"

static const char *TAG = "status";
#define STATUS_PERIOD_MS 60000

static TaskHandle_t s_task;

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
    };
    char buf[160];
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
    return xTaskCreate(status_task, "status", 4096, NULL, 3, &s_task) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
