#include "core/msg.h"
#include "minitest.h"

#define J(s) s, sizeof(s) - 1

static void test_cmd(void)
{
    CHECK_INT(msg_parse_cmd(J("{\"action\":\"start\"}")), MSG_CMD_START);
    CHECK_INT(msg_parse_cmd(J("{\"action\":\"stop\"}")), MSG_CMD_STOP);
    CHECK_INT(msg_parse_cmd(J("{\"action\":\"reboot\"}")), MSG_CMD_REBOOT);
    CHECK_INT(msg_parse_cmd(J("{\"action\":\"status\"}")), MSG_CMD_STATUS);
    CHECK_INT(msg_parse_cmd(J("{\"action\":\"explode\"}")), MSG_CMD_NONE);
    CHECK_INT(msg_parse_cmd(J("{\"action\":1}")), MSG_CMD_NONE);
    CHECK_INT(msg_parse_cmd(J("{}")), MSG_CMD_NONE);
    CHECK_INT(msg_parse_cmd(J("{")), MSG_CMD_NONE);
    CHECK_INT(msg_parse_cmd(J("")), MSG_CMD_NONE);
    CHECK_INT(msg_parse_cmd(J("[\"stop\"]")), MSG_CMD_NONE);
    CHECK_INT(msg_parse_cmd(J("[\"reboot\"]")), MSG_CMD_NONE);
    const char raw[] = "{\"action\":\"stop\"}JUNK";
    CHECK_INT(msg_parse_cmd(raw, 17), MSG_CMD_STOP);
}

static void test_alert_repeat(void)
{
    CHECK_INT(msg_parse_alert_repeat(J("{\"clip\":\"alert\",\"repeat\":3}")), 3);
    CHECK_INT(msg_parse_alert_repeat(J("{\"clip\":\"alert\",\"repeat\":10}")), 10);
    CHECK_INT(msg_parse_alert_repeat(J("{\"clip\":\"alert\"}")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("{\"repeat\":0}")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("{\"repeat\":11}")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("{\"repeat\":2.5}")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("garbage")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("")), 1);
    CHECK_INT(msg_parse_alert_repeat(J("[3]")), 1);
}

static void test_status(void)
{
    msg_status_t s = {.rssi = -71, .battery_mv = 0, .uptime_s = 3600, .streaming = true, .fw = "0.1.0",
                      .detect_ok = true, .threshold = 0.6f, .dwell_s = 5.0f, .max_gap_s = 3.0f,
                      .cooldown_s = 30.0f};
    char buf[256];
    int n = msg_format_status(buf, sizeof buf, &s);
    CHECK_STR(buf, "{\"rssi\":-71,\"battery_mv\":0,\"uptime_s\":3600,\"streaming\":true,\"fw\":\"0.1.0\","
                   "\"detect_ok\":true,\"threshold\":0.6,\"dwell_s\":5,\"max_gap_s\":3,\"cooldown_s\":30}");
    CHECK_INT(n, (long long)strlen(buf));

    s.streaming = false;
    s.detect_ok = false;
    s.dwell_s = 0.25f;
    msg_format_status(buf, sizeof buf, &s);
    CHECK(strstr(buf, "\"streaming\":false") != NULL);
    CHECK(strstr(buf, "\"detect_ok\":false") != NULL);
    CHECK(strstr(buf, "\"dwell_s\":0.25") != NULL);

    char small[16];
    CHECK_INT(msg_format_status(small, sizeof small, &s), -1);
}

static void test_event(void)
{
    msg_event_t e = {.alert_ms = 1790000000123ULL, .first_seen_ms = 1790000000123ULL - 5200,
                     .dwell_s = 5.2f, .max_score = 0.8346f};
    char buf[128];
    int n = msg_format_event(buf, sizeof buf, &e);
    CHECK_STR(buf, "{\"alert_ms\":1790000000123,\"first_seen_ms\":1789999994923,"
                   "\"dwell_s\":5.20,\"max_score\":0.835}");
    CHECK_INT(n, (long long)strlen(buf));

    msg_event_t unsynced = {.alert_ms = 0, .first_seen_ms = 0, .dwell_s = 5.0f, .max_score = 0.7f};
    msg_format_event(buf, sizeof buf, &unsynced);
    CHECK_STR(buf, "{\"alert_ms\":0,\"first_seen_ms\":0,\"dwell_s\":5.00,\"max_score\":0.700}");

    char small[20];
    CHECK_INT(msg_format_event(small, sizeof small, &e), -1);
}

void test_msg(void)
{
    test_cmd();
    test_alert_repeat();
    test_status();
    test_event();
}
