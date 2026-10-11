#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PROTO_ID_SIZE 13            /* 12 lowercase hex chars + NUL */
/* {id}/image header, little-endian: uint64 capture_ms, uint16 score in permille
 * (0..1000, PROTO_SCORE_FAILED = detection failed), uint16 current dwell in
 * deciseconds (saturates at 65535). */
#define PROTO_HEADER_SIZE 12
#define PROTO_SCORE_FAILED 0xFFFF
#define PROTO_MIN_SYNCED_MS 1704067200000LL /* 2024-01-01T00:00:00Z */

typedef enum {
    PROTO_KIND_UNKNOWN,
    PROTO_KIND_ALERT,
    PROTO_KIND_CMD,
    PROTO_KIND_CONFIG,
} proto_kind_t;

void proto_mac_to_id(const uint8_t mac[6], char out[PROTO_ID_SIZE]);

/* Writes "{id}/{kind}". Returns false if it does not fit. */
bool proto_topic(char *buf, size_t len, const char *id, const char *kind);

/* score < 0 or NaN = detection failed; scores above 1 are clamped. */
void proto_pack_header(uint8_t out[PROTO_HEADER_SIZE], uint64_t capture_ms, float score, uint32_t dwell_ms);

/* {id}/event payload: uint16 LE json_len, JSON, JPEG. Returns the total length,
 * or 0 if it does not fit in `cap`, json_len is 0 or > 65535, or jpeg_len is 0. */
size_t proto_pack_event(uint8_t *out, size_t cap, const char *json, size_t json_len,
                        const uint8_t *jpeg, size_t jpeg_len);

/* epoch_ms if the clock looks synced, otherwise 0 ("use server time"). */
uint64_t proto_capture_ms(int64_t epoch_ms);

/* Kind of an incoming topic addressed to `id`. `topic` need not be NUL-terminated. */
proto_kind_t proto_kind_of(const char *topic, size_t topic_len, const char *id);
