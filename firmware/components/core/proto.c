#include "core/proto.h"

#include <stdio.h>
#include <string.h>

void proto_mac_to_id(const uint8_t mac[6], char out[PROTO_ID_SIZE])
{
    static const char HEX[] = "0123456789abcdef";
    for (int i = 0; i < 6; i++) {
        out[2 * i] = HEX[mac[i] >> 4];
        out[2 * i + 1] = HEX[mac[i] & 0x0f];
    }
    out[12] = '\0';
}

bool proto_topic(char *buf, size_t len, const char *id, const char *kind)
{
    int n = snprintf(buf, len, "%s/%s", id, kind);
    return n > 0 && (size_t)n < len;
}

void proto_pack_header(uint8_t out[PROTO_HEADER_SIZE], uint64_t capture_ms)
{
    for (int i = 0; i < PROTO_HEADER_SIZE; i++) {
        out[i] = (uint8_t)(capture_ms >> (8 * i));
    }
}

uint64_t proto_capture_ms(int64_t epoch_ms)
{
    return epoch_ms >= PROTO_MIN_SYNCED_MS ? (uint64_t)epoch_ms : 0;
}

static bool kind_is(const char *k, size_t klen, const char *name)
{
    return klen == strlen(name) && memcmp(k, name, klen) == 0;
}

proto_kind_t proto_kind_of(const char *topic, size_t topic_len, const char *id)
{
    size_t id_len = strlen(id);
    if (topic_len <= id_len + 1 || memcmp(topic, id, id_len) != 0 || topic[id_len] != '/') {
        return PROTO_KIND_UNKNOWN;
    }
    const char *k = topic + id_len + 1;
    size_t klen = topic_len - id_len - 1;
    if (kind_is(k, klen, "alert")) {
        return PROTO_KIND_ALERT;
    }
    if (kind_is(k, klen, "cmd")) {
        return PROTO_KIND_CMD;
    }
    if (kind_is(k, klen, "config")) {
        return PROTO_KIND_CONFIG;
    }
    return PROTO_KIND_UNKNOWN;
}
