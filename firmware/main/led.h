#pragma once
#include <stdbool.h>

#include "esp_err.h"

/* Status LED on BOARD_LED_GPIO (WS2812). Shows inference state without audio:
 * off = no person in the last frame, green = person in the last frame,
 * red = alert fired (held a short time). Failure to init is not fatal. */
esp_err_t led_init(void);
void led_person(bool seen); /* call once per processed frame */
void led_alert(void);       /* call when a dwell alert fires */
