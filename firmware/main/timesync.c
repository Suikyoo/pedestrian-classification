#include "timesync.h"

#include <sys/time.h>

#include "core/proto.h"
#include "esp_netif_sntp.h"

void timesync_start(void)
{
    esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    esp_netif_sntp_init(&cfg);
}

uint64_t timesync_capture_ms(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return proto_capture_ms((int64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000);
}
