#pragma once
#include <stdint.h>

/* Reconnect delays: 5 s, 10 s, 30 s, then 60 s forever. */
typedef struct {
    uint8_t step;
} backoff_t;

void backoff_reset(backoff_t *b);
uint32_t backoff_next_ms(backoff_t *b);
