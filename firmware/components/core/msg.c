#include "core/msg.h"

#include <stdio.h>
#include <string.h>

#include "cJSON.h"

msg_cmd_t msg_parse_cmd(const char *json, size_t len)
{
    static const struct {
        const char *name;
        msg_cmd_t cmd;
    } ACTIONS[] = {
        {"start", MSG_CMD_START},
        {"stop", MSG_CMD_STOP},
        {"reboot", MSG_CMD_REBOOT},
        {"status", MSG_CMD_STATUS},
    };
    msg_cmd_t result = MSG_CMD_NONE;
    cJSON *root = cJSON_ParseWithLength(json, len);
    if (cJSON_IsObject(root)) {
        const cJSON *action = cJSON_GetObjectItemCaseSensitive(root, "action");
        if (cJSON_IsString(action)) {
            for (size_t i = 0; i < sizeof ACTIONS / sizeof ACTIONS[0]; i++) {
                if (strcmp(action->valuestring, ACTIONS[i].name) == 0) {
                    result = ACTIONS[i].cmd;
                }
            }
        }
    }
    cJSON_Delete(root);
    return result;
}

int msg_parse_alert_repeat(const char *json, size_t len)
{
    int repeat = 1;
    cJSON *root = cJSON_ParseWithLength(json, len);
    if (cJSON_IsObject(root)) {
        const cJSON *r = cJSON_GetObjectItemCaseSensitive(root, "repeat");
        if (cJSON_IsNumber(r)) {
            double v = r->valuedouble;
            if (v >= 1 && v <= 10 && v == (double)(int)v) {
                repeat = (int)v;
            }
        }
    }
    cJSON_Delete(root);
    return repeat;
}

int msg_format_status(char *buf, size_t len, const msg_status_t *s)
{
    int n = snprintf(buf, len,
                     "{\"rssi\":%d,\"battery_mv\":%d,\"uptime_s\":%lu,\"streaming\":%s,\"fw\":\"%s\","
                     "\"detect_ok\":%s,\"threshold\":%g,\"dwell_s\":%g,\"max_gap_s\":%g,\"cooldown_s\":%g}",
                     s->rssi, s->battery_mv, (unsigned long)s->uptime_s,
                     s->streaming ? "true" : "false", s->fw, s->detect_ok ? "true" : "false",
                     (double)s->threshold, (double)s->dwell_s, (double)s->max_gap_s,
                     (double)s->cooldown_s);
    return (n > 0 && (size_t)n < len) ? n : -1;
}

/* Decimal text of v. The host's MinGW printf has no %llu, so format by hand. */
static const char *u64_text(uint64_t v, char buf[21])
{
    char *p = buf + 20;
    *p = '\0';
    do {
        *--p = (char)('0' + (int)(v % 10));
        v /= 10;
    } while (v != 0);
    return p;
}

int msg_format_event(char *buf, size_t len, const msg_event_t *e)
{
    char a[21], f[21];
    int n = snprintf(buf, len, "{\"alert_ms\":%s,\"first_seen_ms\":%s,\"dwell_s\":%.2f,\"max_score\":%.3f}",
                     u64_text(e->alert_ms, a), u64_text(e->first_seen_ms, f),
                     (double)e->dwell_s, (double)e->max_score);
    return (n > 0 && (size_t)n < len) ? n : -1;
}
