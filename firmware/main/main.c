/* Boot sequence. Only module interfaces are used here; no driver, Wi-Fi,
 * LTE, or pin details. */
#include "audio.h"
#include "camera.h"
#include "cmd.h"
#include "config_store.h"
#include "core/proto.h"
#include "detect.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "event.h"
#include "led.h"
#include "mqtt_link.h"
#include "net.h"
#include "sdkconfig.h"
#include "status.h"
#include "stream.h"
#include "timesync.h"

static const char *TAG = "main";

void app_main(void)
{
    ESP_ERROR_CHECK(config_store_init());
    devcfg_t cfg;
    config_store_get(&cfg);

    if (camera_init(&cfg) != ESP_OK) {
        ESP_LOGE(TAG, "camera unavailable; stream will retry and reboot if it keeps failing");
    }
    const bool detect_ready = detect_init() == ESP_OK;
    if (!detect_ready) {
        ESP_LOGE(TAG, "pedestrian detection unavailable: no local alerts until the model is flashed");
    }
    ESP_ERROR_CHECK(audio_init());
    audio_set_volume(cfg.volume);
    audio_play_scale(); /* TODO: remove after amp bring-up */
    led_init(); /* optional: logs a warning and the firmware runs without it */

    ESP_ERROR_CHECK(net_start());
    while (!net_wait_connected(pdMS_TO_TICKS(30000))) {
        ESP_LOGW(TAG, "waiting for network");
    }
    timesync_start();

    /* Topic root follows the MQTT username: one id per broker account, and the
     * broker ACL grants {username}/#. Falls back to the MAC id when no
     * username is set. */
    uint8_t mac[6];
    char id[PROTO_ID_SIZE];
    ESP_ERROR_CHECK(esp_efuse_mac_get_default(mac));
    proto_mac_to_id(mac, id);
    if (CONFIG_MQTT_USERNAME[0] != '\0') {
        strlcpy(id, CONFIG_MQTT_USERNAME, sizeof id);
    }

    ESP_ERROR_CHECK(cmd_start());
    ESP_ERROR_CHECK(status_start());
    const mqtt_link_handlers_t handlers = {
        .on_message = cmd_submit,
        .on_connected = status_request,
        .on_published = NULL,
    };
    ESP_ERROR_CHECK(mqtt_link_start(id, &handlers));
    ESP_ERROR_CHECK(event_start());
    ESP_ERROR_CHECK(stream_start(detect_ready));
    ESP_LOGI(TAG, "running as %s", id);
}
