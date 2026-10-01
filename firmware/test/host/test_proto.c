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

static void test_header(void)
{
    uint8_t h[PROTO_HEADER_SIZE];
    proto_pack_header(h, 0x0102030405060708ULL);
    const uint8_t expected[8] = {0x08, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01};
    CHECK(memcmp(h, expected, 8) == 0);

    proto_pack_header(h, 1727600000123ULL);
    uint64_t back = 0;
    for (int i = 7; i >= 0; i--) {
        back = (back << 8) | h[i];
    }
    CHECK(back == 1727600000123ULL);
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
    test_capture_ms();
    test_kind_of();
}
