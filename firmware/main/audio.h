#pragma once
#include <stdint.h>

#include "esp_err.h"

/* Plays the embedded alert clip (assets/alert.raw: 8-bit unsigned PCM, 16 kHz)
 * as PWM on BOARD_AUDIO_GPIO. */
esp_err_t audio_init(void);
void audio_set_volume(uint8_t volume); /* 0..100 */
void audio_play(int repeat);           /* restarts if already playing */
