#include "core/backoff.h"

static const uint32_t STEPS_MS[] = {5000, 10000, 30000, 60000};
#define STEP_COUNT (sizeof(STEPS_MS) / sizeof(STEPS_MS[0]))

void backoff_reset(backoff_t *b)
{
    b->step = 0;
}

uint32_t backoff_next_ms(backoff_t *b)
{
    uint32_t ms = STEPS_MS[b->step];
    if (b->step < STEP_COUNT - 1) {
        b->step++;
    }
    return ms;
}
