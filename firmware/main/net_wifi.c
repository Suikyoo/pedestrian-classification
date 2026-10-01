#include <string.h>

#include "core/backoff.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/event_groups.h"
#include "net.h"
#include "sdkconfig.h"

static const char *TAG = "net_wifi";
#define BIT_UP BIT0

static EventGroupHandle_t s_events;
static esp_timer_handle_t s_retry_timer;
static backoff_t s_backoff;

static void retry_cb(void *arg)
{
    esp_err_t err = esp_wifi_connect();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "esp_wifi_connect failed: %s", esp_err_to_name(err));
        esp_timer_start_once(s_retry_timer, (uint64_t)backoff_next_ms(&s_backoff) * 1000);
    }
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_events, BIT_UP);
        uint32_t ms = backoff_next_ms(&s_backoff);
        ESP_LOGW(TAG, "disconnected, retry in %lu ms", (unsigned long)ms);
        esp_timer_start_once(s_retry_timer, (uint64_t)ms * 1000);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = data;
        ESP_LOGI(TAG, "got ip " IPSTR, IP2STR(&e->ip_info.ip));
        backoff_reset(&s_backoff);
        xEventGroupSetBits(s_events, BIT_UP);
    }
}

esp_err_t net_start(void)
{
    s_events = xEventGroupCreate();
    backoff_reset(&s_backoff);
    const esp_timer_create_args_t targs = {.callback = retry_cb, .name = "wifi_retry"};
    ESP_ERROR_CHECK(esp_timer_create(&targs, &s_retry_timer));

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL));

    wifi_config_t wc = {0};
    strlcpy((char *)wc.sta.ssid, CONFIG_WIFI_SSID, sizeof wc.sta.ssid);
    strlcpy((char *)wc.sta.password, CONFIG_WIFI_PASSWORD, sizeof wc.sta.password);
    wc.sta.threshold.authmode = strlen(CONFIG_WIFI_PASSWORD) ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE)); /* lower latency for frame uploads */
    if (CONFIG_WIFI_SSID[0] == '\0') {
        ESP_LOGE(TAG, "WIFI_SSID is empty: set it in menuconfig > Pedestrian Edge");
    }
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "connecting to \"%s\"", CONFIG_WIFI_SSID);
    return ESP_OK;
}

bool net_wait_connected(TickType_t timeout)
{
    return xEventGroupWaitBits(s_events, BIT_UP, pdFALSE, pdTRUE, timeout) & BIT_UP;
}

int net_rssi(void)
{
    wifi_ap_record_t ap;
    return esp_wifi_sta_get_ap_info(&ap) == ESP_OK ? ap.rssi : 0;
}
