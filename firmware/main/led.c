#include "led.h"

#include <stdint.h>

#include "board.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "led_strip.h"

static const char *TAG = "led";
#define LEVEL 24            /* dim: the WS2812 is bright at full scale */
#define ALERT_HOLD_US 2000000

static led_strip_handle_t s_strip;
static int64_t s_alert_until_us;

static void show(uint8_t r, uint8_t g, uint8_t b)
{
    if (s_strip == NULL) {
        return;
    }
    led_strip_set_pixel(s_strip, 0, r, g, b);
    led_strip_refresh(s_strip);
}

esp_err_t led_init(void)
{
    led_strip_config_t strip_cfg = {
        .strip_gpio_num = BOARD_LED_GPIO,
        .max_leds = 1,
    };
    led_strip_rmt_config_t rmt_cfg = {
        .resolution_hz = 10 * 1000 * 1000,
    };
    esp_err_t err = led_strip_new_rmt_device(&strip_cfg, &rmt_cfg, &s_strip);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "init failed: %s", esp_err_to_name(err));
        s_strip = NULL;
        return err;
    }
    led_strip_clear(s_strip);
    ESP_LOGI(TAG, "ready on GPIO %d", BOARD_LED_GPIO);
    return ESP_OK;
}

void led_person(bool seen)
{
    if (esp_timer_get_time() < s_alert_until_us) {
        return; /* keep the alert colour visible */
    }
    show(0, seen ? LEVEL : 0, 0);
}

void led_alert(void)
{
    s_alert_until_us = esp_timer_get_time() + ALERT_HOLD_US;
    show(LEVEL, 0, 0);
}
