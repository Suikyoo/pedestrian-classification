#include "event.h"

#include <string.h>

#include "core/msg.h"
#include "core/proto.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mqtt_link.h"

static const char *TAG = "event";
#define EVENT_QUEUE_LEN 4
#define RETRY_MS 1000
#define ACK_TIMEOUT_MS 15000

typedef struct {
    uint8_t *data;
    size_t len;
} pending_t;

static pending_t s_queue[EVENT_QUEUE_LEN]; /* s_queue[0] is the oldest */
static int s_count;
static bool s_sending; /* s_queue[0] is being published or awaits its PUBACK: never drop it */
static int s_inflight_id = -1; /* msg id of the pending publish, -1 until publish returns */
static int64_t s_sent_us;
static SemaphoreHandle_t s_lock;
static TaskHandle_t s_task;

static void remove_at(int i)
{
    heap_caps_free(s_queue[i].data);
    memmove(&s_queue[i], &s_queue[i + 1], (size_t)(s_count - i - 1) * sizeof s_queue[0]);
    s_count--;
}

void event_raise(float score, uint64_t capture_ms, const uint8_t *jpeg, size_t len)
{
    msg_event_t ev = {
        .alert_ms = capture_ms,
        .first_seen_ms = capture_ms,
        .dwell_s = 0.0f,
        .max_score = score,
    };
    char json[128];
    int n = msg_format_event(json, sizeof json, &ev);
    if (n < 0) {
        ESP_LOGE(TAG, "event JSON does not fit");
        return;
    }
    size_t cap = 2 + (size_t)n + len;
    uint8_t *buf = heap_caps_malloc(cap, MALLOC_CAP_SPIRAM);
    if (buf == NULL) {
        ESP_LOGW(TAG, "no memory for %u-byte event", (unsigned)cap);
        return;
    }
    size_t total = proto_pack_event(buf, cap, json, (size_t)n, jpeg, len);
    if (total == 0) {
        heap_caps_free(buf);
        ESP_LOGE(TAG, "event packing failed");
        return;
    }

    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (s_count == EVENT_QUEUE_LEN) {
        remove_at(s_sending ? 1 : 0);
        ESP_LOGW(TAG, "event queue full: dropped the oldest waiting event");
    }
    s_queue[s_count].data = buf;
    s_queue[s_count].len = total;
    s_count++;
    xSemaphoreGive(s_lock);
    xTaskNotifyGive(s_task);
}

/* Called on the MQTT task when the broker acknowledged a QoS 1 publish. */
void event_on_published(int msg_id)
{
    if (s_lock == NULL) {
        return;
    }
    bool delivered = false;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (s_sending && s_inflight_id >= 0 && msg_id == s_inflight_id) {
        remove_at(0);
        s_sending = false;
        s_inflight_id = -1;
        delivered = true;
    }
    xSemaphoreGive(s_lock);
    if (delivered) {
        ESP_LOGI(TAG, "event delivered");
        xTaskNotifyGive(s_task); /* send the next one */
    }
}

static void event_task(void *arg)
{
    for (;;) {
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(RETRY_MS));

        bool connected = mqtt_link_connected();
        pending_t head = {NULL, 0};
        xSemaphoreTake(s_lock, portMAX_DELAY);
        if (s_sending && s_inflight_id >= 0 &&
            (!connected || esp_timer_get_time() - s_sent_us > (int64_t)ACK_TIMEOUT_MS * 1000)) {
            /* The head stays queued and is sent again. */
            s_sending = false;
            s_inflight_id = -1;
            ESP_LOGW(TAG, "event not acknowledged, resending");
        }
        if (!s_sending && connected && s_count > 0) {
            head = s_queue[0];
            /* Set before releasing the lock so event_raise() cannot drop the head
             * while it is being published. */
            s_sending = true;
            s_inflight_id = -1;
        }
        xSemaphoreGive(s_lock);
        if (head.data == NULL) {
            continue;
        }

        /* Publishing a large JPEG takes a while: do it outside the lock. */
        int id = mqtt_link_publish("event", head.data, head.len, 1, false);
        xSemaphoreTake(s_lock, portMAX_DELAY);
        if (id >= 0) {
            s_inflight_id = id;
            s_sent_us = esp_timer_get_time();
        } else {
            s_sending = false;
        }
        xSemaphoreGive(s_lock);
        if (id < 0) {
            ESP_LOGW(TAG, "event publish failed, retrying in %d ms", RETRY_MS);
        } else {
            ESP_LOGI(TAG, "event sent, waiting for acknowledgement");
        }
    }
}

esp_err_t event_start(void)
{
    s_lock = xSemaphoreCreateMutex();
    if (s_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }
    return xTaskCreate(event_task, "event", 4096, NULL, 4, &s_task) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
}
