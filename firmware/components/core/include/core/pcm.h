#pragma once
#include <stdint.h>

/* Scale an 8-bit unsigned sample (silence = 128) by volume 0..100. */
static inline uint8_t pcm_scale(uint8_t sample, uint8_t volume)
{
    if (volume > 100) {
        volume = 100;
    }
    int centered = (int)sample - 128;
    return (uint8_t)(128 + centered * (int)volume / 100);
}
