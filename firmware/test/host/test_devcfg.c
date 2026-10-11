#include "core/devcfg.h"
#include "minitest.h"

#define J(s) s, sizeof(s) - 1

static void test_defaults(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK_INT(c.interval_ms, 1000);
    CHECK_INT(c.jpeg_quality, 12);
    CHECK_INT(c.frame_size, DEVCFG_FRAME_VGA);
    CHECK_INT(c.volume, 80);
    CHECK(!c.streaming); /* empty scenes send nothing until master says start */
    CHECK(c.threshold == 0.6f);
    CHECK(c.dwell_s == 5.0f);
    CHECK(c.max_gap_s == 3.0f);
    CHECK(c.cooldown_s == 30.0f);
}

static void test_partial_update_keeps_other_fields(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"volume\":60}")));
    CHECK_INT(c.volume, 60);
    CHECK_INT(c.interval_ms, 1000);
    CHECK_INT(c.frame_size, DEVCFG_FRAME_VGA);
}

static void test_full_update(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"interval_ms\":500,\"jpeg_quality\":20,"
                                  "\"frame_size\":\"SVGA\",\"volume\":10}")));
    CHECK_INT(c.interval_ms, 500);
    CHECK_INT(c.jpeg_quality, 20);
    CHECK_INT(c.frame_size, DEVCFG_FRAME_SVGA);
    CHECK_INT(c.volume, 10);
    CHECK(!c.streaming);
}

static void test_bounds_accepted(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"interval_ms\":100,\"jpeg_quality\":0,\"volume\":0}")));
    CHECK(devcfg_apply_json(&c, J("{\"interval_ms\":3600000,\"jpeg_quality\":63,\"volume\":100}")));
    CHECK_INT(c.interval_ms, 3600000);
    CHECK_INT(c.jpeg_quality, 63);
    CHECK_INT(c.volume, 100);
}

static void test_unknown_fields_ignored(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"volume\":70,\"color\":\"red\",\"streaming\":true}")));
    CHECK_INT(c.volume, 70);
    CHECK(!c.streaming); /* streaming is changed only by start/stop */
}

static void test_invalid_rejects_whole_update(void)
{
    static const char *const BAD[] = {
        "{\"volume\":20,\"interval_ms\":50}",
        "{\"volume\":101}",
        "{\"volume\":-1}",
        "{\"volume\":1.5}",
        "{\"volume\":\"loud\"}",
        "{\"volume\":true}",
        "{\"jpeg_quality\":64}",
        "{\"interval_ms\":3600001}",
        "{\"frame_size\":\"vga\"}",
        "{\"frame_size\":3}",
        "{\"threshold\":1.0}",
        "{\"threshold\":0.01}",
        "{\"threshold\":\"high\"}",
        "{\"threshold\":true}",
        "{\"dwell_s\":600.5}",
        "{\"dwell_s\":-1}",
        "{\"max_gap_s\":0.4}",
        "{\"max_gap_s\":61}",
        "{\"cooldown_s\":3601}",
        "{\"cooldown_s\":-0.5}",
        "{\"volume\":50,\"threshold\":2}",
        "{",
        "[1]",
        "0",
        "",
    };
    for (size_t i = 0; i < sizeof BAD / sizeof BAD[0]; i++) {
        devcfg_t c, before;
        devcfg_defaults(&c);
        before = c;
        if (devcfg_apply_json(&c, BAD[i], strlen(BAD[i]))) {
            printf("accepted bad config: %s\n", BAD[i]);
            CHECK(0);
        }
        CHECK(devcfg_equal(&c, &before));
    }
}

static void test_respects_length(void)
{
    /* Not NUL-terminated; trailing bytes are not part of the payload. */
    const char buf[] = {'{', '"', 'v', 'o', 'l', 'u', 'm', 'e', '"', ':', '5', '}', 'x', 'x'};
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, buf, 12));
    CHECK_INT(c.volume, 5);
}

static void test_equal(void)
{
    devcfg_t a, b;
    devcfg_defaults(&a);
    devcfg_defaults(&b);
    CHECK(devcfg_equal(&a, &b));
    CHECK(devcfg_apply_json(&b, J("{\"volume\":80}")));
    CHECK(devcfg_equal(&a, &b)); /* same value re-applied */
    b.streaming = true;
    CHECK(!devcfg_equal(&a, &b));
}

static void test_frame_names(void)
{
    for (int f = 0; f < DEVCFG_FRAME_COUNT; f++) {
        devcfg_frame_t back;
        CHECK(devcfg_frame_from_name(devcfg_frame_name((devcfg_frame_t)f), &back));
        CHECK_INT(back, f);
    }
    CHECK_STR(devcfg_frame_name(DEVCFG_FRAME_HD), "HD");
    CHECK(devcfg_frame_name(DEVCFG_FRAME_COUNT) == NULL);
    devcfg_frame_t out;
    CHECK(!devcfg_frame_from_name("4K", &out));
}

static void test_valid(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_valid(&c));

    devcfg_defaults(&c); c.interval_ms = 0;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.interval_ms = 99;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.interval_ms = 3600001;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.jpeg_quality = 64;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.frame_size = DEVCFG_FRAME_COUNT;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.volume = 101;
    CHECK(!devcfg_valid(&c));

    devcfg_defaults(&c); c.interval_ms = 100;
    CHECK(devcfg_valid(&c));
    devcfg_defaults(&c); c.interval_ms = 3600000;
    CHECK(devcfg_valid(&c));
    devcfg_defaults(&c); c.jpeg_quality = 0;
    CHECK(devcfg_valid(&c));
    devcfg_defaults(&c); c.jpeg_quality = 63;
    CHECK(devcfg_valid(&c));
    devcfg_defaults(&c); c.volume = 0;
    CHECK(devcfg_valid(&c));
    devcfg_defaults(&c); c.volume = 100;
    CHECK(devcfg_valid(&c));
    devcfg_defaults(&c); c.frame_size = DEVCFG_FRAME_UXGA;
    CHECK(devcfg_valid(&c));
    devcfg_defaults(&c); c.streaming = false;
    CHECK(devcfg_valid(&c));
}

static void test_detection_fields_update(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"threshold\":0.45,\"dwell_s\":2.5,"
                                  "\"max_gap_s\":1,\"cooldown_s\":0}")));
    CHECK(c.threshold == 0.45f);
    CHECK(c.dwell_s == 2.5f);
    CHECK(c.max_gap_s == 1.0f);
    CHECK(c.cooldown_s == 0.0f);
    CHECK_INT(c.volume, 80); /* untouched */
}

static void test_detection_bounds_accepted(void)
{
    devcfg_t c;
    devcfg_defaults(&c);
    CHECK(devcfg_apply_json(&c, J("{\"threshold\":0.05,\"dwell_s\":0,\"max_gap_s\":0.5,\"cooldown_s\":0}")));
    CHECK(devcfg_valid(&c));
    CHECK(devcfg_apply_json(&c, J("{\"threshold\":0.99,\"dwell_s\":600,\"max_gap_s\":60,\"cooldown_s\":3600}")));
    CHECK(devcfg_valid(&c));
    CHECK(c.threshold == 0.99f);
    CHECK(c.cooldown_s == 3600.0f);
}

static void test_detection_fields_valid(void)
{
    devcfg_t c;
    devcfg_defaults(&c); c.threshold = 0.04f;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.threshold = 1.0f;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.threshold = 0.0f / 0.0f; /* NaN */
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.dwell_s = 601.0f;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.max_gap_s = 0.0f;
    CHECK(!devcfg_valid(&c));
    devcfg_defaults(&c); c.cooldown_s = -1.0f;
    CHECK(!devcfg_valid(&c));
}

static void test_equal_covers_detection_fields(void)
{
    devcfg_t a, b;
    devcfg_defaults(&a);
    devcfg_defaults(&b);
    b.dwell_s = 6.0f;
    CHECK(!devcfg_equal(&a, &b));
    devcfg_defaults(&b);
    b.threshold = 0.7f;
    CHECK(!devcfg_equal(&a, &b));
}

void test_devcfg(void)
{
    test_defaults();
    test_partial_update_keeps_other_fields();
    test_full_update();
    test_bounds_accepted();
    test_unknown_fields_ignored();
    test_invalid_rejects_whole_update();
    test_respects_length();
    test_equal();
    test_frame_names();
    test_valid();
    test_detection_fields_update();
    test_detection_bounds_accepted();
    test_detection_fields_valid();
    test_equal_covers_detection_fields();
}
