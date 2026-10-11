#include "core/proto.h"
#include "minitest.h"

static void test_mac_to_id(void)
{
    const uint8_t mac[6] = {0xA1, 0xB2, 0xC3, 0xD4, 0xE5, 0xF6};
    char id[PROTO_ID_SIZE];
    proto_mac_to_id(mac, id);
    CHECK_STR(id, "a1b2c3d4e5f6");
}

static void test_topic(void)
{
    char buf[32];
    CHECK(proto_topic(buf, sizeof buf, "a1b2c3d4e5f6", "image"));
    CHECK_STR(buf, "a1b2c3d4e5f6/image");

    char small[10];
    CHECK(!proto_topic(small, sizeof small, "a1b2c3d4e5f6", "image"));
}

static uint64_t le(const uint8_t *p, int n)
{
    uint64_t v = 0;
    for (int i = n - 1; i >= 0; i--) {
        v = (v << 8) | p[i];
    }
    return v;
}

static void test_header(void)
{
    uint8_t h[PROTO_HEADER_SIZE];
    CHECK_INT(PROTO_HEADER_SIZE, 12);

    proto_pack_header(h, 0x0102030405060708ULL, 0.5f, 2000);
    const uint8_t expected[12] = {0x08, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01, 0xF4, 0x01, 0x14, 0x00};
    CHECK(memcmp(h, expected, 12) == 0);

    proto_pack_header(h, 1727600000123ULL, 0.8346f, 5150);
    CHECK(le(h, 8) == 1727600000123ULL);
    CHECK_INT(le(h + 8, 2), 835);
    CHECK_INT(le(h + 10, 2), 51);
}

static void test_header_score_edges(void)
{
    uint8_t h[PROTO_HEADER_SIZE];
    proto_pack_header(h, 0, -1.0f, 0);
    CHECK_INT(le(h + 8, 2), PROTO_SCORE_FAILED);
    proto_pack_header(h, 0, 0.0f / 0.0f, 0); /* NaN counts as failed */
    CHECK_INT(le(h + 8, 2), PROTO_SCORE_FAILED);
    proto_pack_header(h, 0, 0.0f, 0);
    CHECK_INT(le(h + 8, 2), 0);
    proto_pack_header(h, 0, 1.0f, 0);
    CHECK_INT(le(h + 8, 2), 1000);
    proto_pack_header(h, 0, 1.7f, 0);
    CHECK_INT(le(h + 8, 2), 1000);
}

static void test_header_dwell_saturates(void)
{
    uint8_t h[PROTO_HEADER_SIZE];
    proto_pack_header(h, 0, 0.5f, 6553500);
    CHECK_INT(le(h + 10, 2), 65535);
    proto_pack_header(h, 0, 0.5f, 7000000);
    CHECK_INT(le(h + 10, 2), 65535);
    proto_pack_header(h, 0, 0.5f, 99);
    CHECK_INT(le(h + 10, 2), 0);
}

static void test_pack_event(void)
{
    const char json[] = "{\"a\":1}";
    const uint8_t jpeg[] = {0xFF, 0xD8, 0x01};
    uint8_t out[32];
    size_t n = proto_pack_event(out, sizeof out, json, 7, jpeg, 3);
    CHECK_INT(n, 12);
    CHECK_INT(le(out, 2), 7);
    CHECK(memcmp(out + 2, json, 7) == 0);
    CHECK(memcmp(out + 9, jpeg, 3) == 0);

    CHECK_INT(proto_pack_event(out, 11, json, 7, jpeg, 3), 0);   /* does not fit */
    CHECK_INT(proto_pack_event(out, sizeof out, json, 0, jpeg, 3), 0); /* no JSON */
    CHECK_INT(proto_pack_event(out, sizeof out, json, 7, jpeg, 0), 0); /* no snapshot */
    CHECK_INT(proto_pack_event(out, (size_t)-1, json, 70000, jpeg, 3), 0); /* JSON too long for u16 */
}

static void test_capture_ms(void)
{
    CHECK(proto_capture_ms(0) == 0);
    CHECK(proto_capture_ms(-5) == 0);
    CHECK(proto_capture_ms(1704067199999LL) == 0);
    CHECK(proto_capture_ms(1704067200000LL) == 1704067200000ULL);
    CHECK(proto_capture_ms(1790000000000LL) == 1790000000000ULL);
}

static void test_kind_of(void)
{
    const char *id = "a1b2c3d4e5f6";
#define KIND(t) proto_kind_of(t, strlen(t), id)
    CHECK_INT(KIND("a1b2c3d4e5f6/alert"), PROTO_KIND_ALERT);
    CHECK_INT(KIND("a1b2c3d4e5f6/cmd"), PROTO_KIND_CMD);
    CHECK_INT(KIND("a1b2c3d4e5f6/config"), PROTO_KIND_CONFIG);
    CHECK_INT(KIND("a1b2c3d4e5f6/image"), PROTO_KIND_UNKNOWN);
    CHECK_INT(KIND("a1b2c3d4e5f6/alertx"), PROTO_KIND_UNKNOWN);
    CHECK_INT(KIND("a1b2c3d4e5f6/"), PROTO_KIND_UNKNOWN);
    CHECK_INT(KIND("a1b2c3d4e5f6"), PROTO_KIND_UNKNOWN);
    CHECK_INT(KIND("000000000000/alert"), PROTO_KIND_UNKNOWN);
    CHECK_INT(KIND(""), PROTO_KIND_UNKNOWN);
#undef KIND
    /* Not NUL-terminated: only the first 16 bytes are the topic. */
    const char raw[] = "a1b2c3d4e5f6/cmdGARBAGE";
    CHECK_INT(proto_kind_of(raw, 16, id), PROTO_KIND_CMD);
}

void test_proto(void)
{
    test_mac_to_id();
    test_topic();
    test_header();
    test_header_score_edges();
    test_header_dwell_saturates();
    test_pack_event();
    test_capture_ms();
    test_kind_of();
}
