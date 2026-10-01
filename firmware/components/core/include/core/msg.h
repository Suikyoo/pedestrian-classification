#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
    MSG_CMD_NONE,
    MSG_CMD_START,
    MSG_CMD_STOP,
    MSG_CMD_REBOOT,
    MSG_CMD_STATUS,
} msg_cmd_t;

/* Parse {id}/cmd payload {"action":"..."}. MSG_CMD_NONE if invalid. */
msg_cmd_t msg_parse_cmd(const char *json, size_t len);

/* Parse {id}/alert payload; returns repeat 1..10 (1 if missing or invalid). */
int msg_parse_alert_repeat(const char *json, size_t len);

typedef struct {
    int rssi;
    int battery_mv;
    uint32_t uptime_s;
    bool streaming;
    const char *fw;   /* must not contain quotes or backslashes */
} msg_status_t;

/* Format {id}/status JSON. Returns its length, or -1 if it does not fit. */
int msg_format_status(char *buf, size_t len, const msg_status_t *s);
