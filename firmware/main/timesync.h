#pragma once
#include <stdint.h>

void timesync_start(void);         /* start SNTP; call after the network is up */
uint64_t timesync_capture_ms(void); /* epoch ms, or 0 while the clock is not synced */
