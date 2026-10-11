#include "event.h"

#include <string.h>

#include "core/msg.h"
#include "core/proto.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mqtt_link.h"

static const char *TAG = "event";
#define EVENT_QUEUE_LEN 4
#define RETRY_MS 1000

typedef struct {
    uint8_t *data;
    size_t len;
} pending_t;

static pending_t s_queue[EVENT_QUEUE_LEN]; /* s_queue[0] is the oldest */
static int s_count;
static bool s_sending; /* s_queue[0] is being published: never drop it */
static SemaphoreHandle_t s_lock;
static TaskHandle_t s_task;

static void remove_at(int i)
{
    heap_caps_free(s_queue[i].data);
    memmove(&s_queue[i], &s_queue[i + 1], (size_t)(s_count - i - 1) * sizeof s_queue[0]);
    s_count--;
}

void event_raise(const dwell_alert_t *a, uint64_t capture_ms, const uint8_t *jpeg, size_t len)
{
    uint32_t dwell_ms = (uint32_t)(a->alert_ms - a->first_seen_ms);
    msg_event_t ev = {
        .alert_ms = capture_ms,
        .first_seen_ms = capture_ms ? capture_ms - dwell_ms : 0,
        .dwell_s = dwell_ms / 1000.0f,
        .max_score = a->max_score,
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

static void event_task(void *arg)
{
    for (;;) {
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(RETRY_MS));
        while (mqtt_link_connected()) {
            xSemaphoreTake(s_lock, portMAX_DELAY);
            pending_t head = s_count ? s_queue[0] : (pending_t){NULL, 0};
            s_sending = head.data != NULL;
            xSemaphoreGive(s_lock);
            if (head.data == NULL) {
                break;
            }
            /* Publishing a large JPEG takes a while: do it outside the lock.
             * event_raise() never drops s_queue[0] while s_sending is set. */
            int id = mqtt_link_publish("event", head.data, head.len, 1, false);
            xSemaphoreTake(s_lock, portMAX_DELAY);
            s_sending = false;
            if (id >= 0) {
                remove_at(0);
            }
            xSemaphoreGive(s_lock);
            if (id < 0) {
                ESP_LOGW(TAG, "event publish failed, retrying in %d ms", RETRY_MS);
                break;
            }
            ESP_LOGI(TAG, "event sent");
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
