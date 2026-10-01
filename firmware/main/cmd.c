#include "cmd.h"

#include <string.h>

#include "audio.h"
#include "camera.h"
#include "config_store.h"
#include "core/devcfg.h"
#include "core/msg.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "status.h"

static const char *TAG = "cmd";
#define CMD_MAX_PAYLOAD 256

typedef struct {
    proto_kind_t kind;
    uint16_t len;
    char data[CMD_MAX_PAYLOAD];
} cmd_msg_t;

static QueueHandle_t s_queue;

void cmd_submit(proto_kind_t kind, const char *data, size_t len)
{
    if (len >= CMD_MAX_PAYLOAD) {
        ESP_LOGW(TAG, "dropping %u-byte message (max %d)", (unsigned)len, CMD_MAX_PAYLOAD - 1);
        return;
    }
    cmd_msg_t m = {.kind = kind, .len = (uint16_t)len};
    memcpy(m.data, data, len);
    if (xQueueSend(s_queue, &m, 0) != pdTRUE) {
        ESP_LOGW(TAG, "command queue full, dropping message");
    }
}

static void set_streaming(bool on)
{
    devcfg_t c;
    config_store_get(&c);
    c.streaming = on;
    config_store_set(&c);
    ESP_LOGI(TAG, "streaming %s", on ? "on" : "off");
}

static void handle_config(const char *data, size_t len)
{
    devcfg_t cur, next;
    config_store_get(&cur);
    next = cur;
    if (!devcfg_apply_json(&next, data, len)) {
        ESP_LOGW(TAG, "rejected config: %.*s", (int)len, data);
        return;
    }
    config_store_set(&next);
    if (next.frame_size != cur.frame_size || next.jpeg_quality != cur.jpeg_quality) {
        camera_apply(&next);
    }
    audio_set_volume(next.volume);
    ESP_LOGI(TAG, "config: interval_ms=%lu quality=%u frame=%s volume=%u",
             (unsigned long)next.interval_ms, next.jpeg_quality,
             devcfg_frame_name(next.frame_size), next.volume);
}

static void handle_cmd(const char *data, size_t len)
{
    switch (msg_parse_cmd(data, len)) {
    case MSG_CMD_START:
        set_streaming(true);
        break;
    case MSG_CMD_STOP:
        set_streaming(false);
        break;
    case MSG_CMD_STATUS:
        status_request();
        break;
    case MSG_CMD_REBOOT:
        ESP_LOGW(TAG, "reboot requested");
        vTaskDelay(pdMS_TO_TICKS(200));
        esp_restart();
        break;
    case MSG_CMD_NONE:
        ESP_LOGW(TAG, "unknown cmd: %.*s", (int)len, data);
        break;
    }
}

static void cmd_task(void *arg)
{
    cmd_msg_t m;
    for (;;) {
        if (xQueueReceive(s_queue, &m, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        switch (m.kind) {
        case PROTO_KIND_ALERT:
            audio_play(msg_parse_alert_repeat(m.data, m.len));
            break;
        case PROTO_KIND_CMD:
            handle_cmd(m.data, m.len);
            break;
        case PROTO_KIND_CONFIG:
            handle_config(m.data, m.len);
            break;
        default:
            break;
        }
    }
}

esp_err_t cmd_start(void)
{
    s_queue = xQueueCreate(8, sizeof(cmd_msg_t));
    if (s_queue == NULL) {
        return ESP_ERR_NO_MEM;
    }
    return xTaskCreate(cmd_task, "cmd", 4096, NULL, 5, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
