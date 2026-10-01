#include "stream.h"

#include <string.h>

#include "camera.h"
#include "config_store.h"
#include "core/proto.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mqtt_link.h"
#include "timesync.h"

static const char *TAG = "stream";
#define MAX_CAPTURE_FAILURES 5
#define SLICE_MS 100

static int s_failures;

static void send_frame(const devcfg_t *cfg)
{
    camera_fb_t *fb = camera_capture();
    if (fb == NULL) {
        if (++s_failures >= MAX_CAPTURE_FAILURES) {
            ESP_LOGE(TAG, "%d capture failures, re-initializing camera", s_failures);
            if (camera_reinit(cfg) != ESP_OK) {
                ESP_LOGE(TAG, "camera re-init failed, rebooting");
                esp_restart();
            }
            s_failures = 0;
        }
        return;
    }
    s_failures = 0;

    size_t n = PROTO_HEADER_SIZE + fb->len;
    uint8_t *buf = heap_caps_malloc(n, MALLOC_CAP_SPIRAM);
    if (buf == NULL) {
        ESP_LOGW(TAG, "no memory for %u-byte frame", (unsigned)n);
        camera_return(fb);
        return;
    }
    proto_pack_header(buf, timesync_capture_ms());
    memcpy(buf + PROTO_HEADER_SIZE, fb->buf, fb->len);
    camera_return(fb);

    if (mqtt_link_publish("image", buf, n, 0, false) < 0) {
        ESP_LOGW(TAG, "publish failed");
    }
    heap_caps_free(buf);
}

static void stream_task(void *arg)
{
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
    for (;;) {
        devcfg_t cfg;
        config_store_get(&cfg);
        int64_t started = esp_timer_get_time();
        if (cfg.streaming && mqtt_link_connected()) {
            send_frame(&cfg);
        }
        /* Sleep in slices so the watchdog is fed and config changes apply quickly. */
        for (;;) {
            esp_task_wdt_reset();
            config_store_get(&cfg);
            if ((esp_timer_get_time() - started) / 1000 >= cfg.interval_ms) {
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(SLICE_MS));
        }
    }
}

esp_err_t stream_start(void)
{
    return xTaskCreate(stream_task, "stream", 6144, NULL, 4, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
