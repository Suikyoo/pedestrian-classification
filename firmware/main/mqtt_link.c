#include "mqtt_link.h"

#include <string.h>

#include "esp_crt_bundle.h"
#include "esp_log.h"
#include "mqtt_client.h"
#include "sdkconfig.h"

static const char *TAG = "mqtt_link";

static esp_mqtt_client_handle_t s_client;
static char s_id[PROTO_ID_SIZE];
static char s_will_topic[32];
static mqtt_link_handlers_t s_handlers;
static volatile bool s_connected;

static void subscribe_all(void)
{
    static const char *const KINDS[] = {"alert", "cmd", "config"};
    char topic[32];
    for (size_t i = 0; i < sizeof KINDS / sizeof KINDS[0]; i++) {
        if (proto_topic(topic, sizeof topic, s_id, KINDS[i])) {
            esp_mqtt_client_subscribe(s_client, topic, 1);
        }
    }
}

static void on_event(void *arg, esp_event_base_t base, int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t e = event_data;
    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "connected");
        s_connected = true;
        esp_mqtt_client_publish(s_client, s_will_topic, "1", 1, 1, 1);
        subscribe_all();
        if (s_handlers.on_connected) {
            s_handlers.on_connected();
        }
        break;
    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "disconnected");
        s_connected = false;
        break;
    case MQTT_EVENT_DATA:
        /* Commands are small; drop anything that arrives in fragments. */
        if (e->current_data_offset != 0 || e->data_len != e->total_data_len) {
            ESP_LOGW(TAG, "dropping fragmented message (%d bytes)", e->total_data_len);
            break;
        }
        proto_kind_t kind = proto_kind_of(e->topic, (size_t)e->topic_len, s_id);
        if (kind != PROTO_KIND_UNKNOWN && s_handlers.on_message) {
            s_handlers.on_message(kind, e->data, (size_t)e->data_len);
        }
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGW(TAG, "transport error");
        break;
    default:
        break;
    }
}

esp_err_t mqtt_link_start(const char *device_id, const mqtt_link_handlers_t *handlers)
{
    strlcpy(s_id, device_id, sizeof s_id);
    s_handlers = *handlers;
    if (!proto_topic(s_will_topic, sizeof s_will_topic, s_id, "online")) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_mqtt_client_config_t cfg = {
        .broker.address.uri = CONFIG_MQTT_URI,
        .broker.verification.crt_bundle_attach = esp_crt_bundle_attach,
        .credentials.client_id = s_id,
        .credentials.username = CONFIG_MQTT_USERNAME[0] ? CONFIG_MQTT_USERNAME : NULL,
        .credentials.authentication.password = CONFIG_MQTT_PASSWORD[0] ? CONFIG_MQTT_PASSWORD : NULL,
        .session.keepalive = 30,
        .session.last_will = {
            .topic = s_will_topic,
            .msg = "0",
            .msg_len = 1,
            .qos = 1,
            .retain = 1,
        },
        .network.reconnect_timeout_ms = 5000,
        .buffer.size = 4096,
        .buffer.out_size = 160 * 1024, /* whole JPEG frame + header; allocated in PSRAM */
    };
    s_client = esp_mqtt_client_init(&cfg);
    if (s_client == NULL) {
        return ESP_FAIL;
    }
    esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, on_event, NULL);
    ESP_LOGI(TAG, "device id %s, broker %s", s_id, CONFIG_MQTT_URI);
    return esp_mqtt_client_start(s_client);
}

bool mqtt_link_connected(void)
{
    return s_connected;
}

int mqtt_link_publish(const char *kind, const void *data, size_t len, int qos, bool retain)
{
    char topic[32];
    if (!s_connected || !proto_topic(topic, sizeof topic, s_id, kind)) {
        return -1;
    }
    return esp_mqtt_client_publish(s_client, topic, data, (int)len, qos, retain);
}
