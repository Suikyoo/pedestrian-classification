#include "stream.h"

#include <string.h>

#include "audio.h"
#include "camera.h"
#include "config_store.h"
#include "core/proto.h"
#include "detect.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "event.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "led.h"
#include "mqtt_link.h"
#include "status.h"
#include "timesync.h"

static const char *TAG = "stream";
#define MAX_CAPTURE_FAILURES 5
#define MAX_DETECT_FAILURES 5
#define SLICE_MS 100
#define ALERT_THRESHOLD 0.90f /* immediate local alert cutoff; same constant on the host */
#define ALERT_COOLDOWN_S 5    /* min time between local alerts */

static int s_failures;
static int s_detect_failures;
static volatile bool s_detect_ok = true;
static int64_t s_last_event_us;
static int64_t s_last_local_alert_us;

bool stream_detect_ok(void)
{
    return s_detect_ok;
}

static void track_detect(float score)
{
    if (score >= 0.0f) {
        s_detect_failures = 0;
        if (!s_detect_ok) {
            s_detect_ok = true;
            ESP_LOGI(TAG, "detection recovered");
            status_request();
        }
    } else if (++s_detect_failures == MAX_DETECT_FAILURES) {
        s_detect_ok = false;
        ESP_LOGE(TAG, "%d detection failures in a row", MAX_DETECT_FAILURES);
        status_request();
    }
}

static void send_frame(const camera_fb_t *fb, uint64_t capture_ms, float score, uint32_t dwell_ms)
{
    size_t n = PROTO_HEADER_SIZE + fb->len;
    uint8_t *buf = heap_caps_malloc(n, MALLOC_CAP_SPIRAM);
    if (buf == NULL) {
        ESP_LOGW(TAG, "no memory for %u-byte frame", (unsigned)n);
        return;
    }
    proto_pack_header(buf, capture_ms, score, dwell_ms);
    memcpy(buf + PROTO_HEADER_SIZE, fb->buf, fb->len);
    if (mqtt_link_publish("image", buf, n, 0, false) < 0) {
        ESP_LOGW(TAG, "publish failed");
    }
    heap_caps_free(buf);
}

static void process_frame(const devcfg_t *cfg)
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

    uint64_t capture_ms = timesync_capture_ms();
    float score = detect_score(fb->buf, fb->len);
    track_detect(score);

    int64_t now_us = esp_timer_get_time();
    bool positive = score >= cfg->threshold;
    led_person(positive);
    /* Candidate event per positive frame, rate-capped by cooldown_s. The host
     * verifies and commands the alert. */
    if (positive && now_us - s_last_event_us >= (int64_t)cfg->cooldown_s * 1000000) {
        s_last_event_us = now_us;
        event_raise(score, capture_ms, fb->buf, fb->len);
    }
    /* Escape hatch: very confident local score alerts without the host. */
    if (score > ALERT_THRESHOLD &&
        now_us - s_last_local_alert_us >= (int64_t)ALERT_COOLDOWN_S * 1000000) {
        s_last_local_alert_us = now_us;
        ESP_LOGI(TAG, "LOCAL ALERT score=%.2f", score);
        led_alert();
        audio_play(1);
    }
    if (cfg->streaming && mqtt_link_connected()) {
        send_frame(fb, capture_ms, score, 0);
    }
    camera_return(fb);
}

static void stream_task(void *arg)
{
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
    for (;;) {
        devcfg_t cfg;
        config_store_get(&cfg);
        int64_t started = esp_timer_get_time();
        process_frame(&cfg);
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

esp_err_t stream_start(bool detect_ready)
{
    s_detect_ok = detect_ready;
    /* ESP-DL inference runs on this task: give it a larger stack. */
    return xTaskCreate(stream_task, "stream", 16384, NULL, 4, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
