#pragma once

#define BOARD_NAME "freenove-s3cam"

/* OV2640 on the 24-pin FPC (same pinout as ESP32-S3-EYE). */
#define BOARD_CAM_PIN_PWDN -1
#define BOARD_CAM_PIN_RESET -1
#define BOARD_CAM_PIN_XCLK 15
#define BOARD_CAM_PIN_SIOD 4
#define BOARD_CAM_PIN_SIOC 5
#define BOARD_CAM_PIN_D0 11
#define BOARD_CAM_PIN_D1 9
#define BOARD_CAM_PIN_D2 8
#define BOARD_CAM_PIN_D3 10
#define BOARD_CAM_PIN_D4 12
#define BOARD_CAM_PIN_D5 18
#define BOARD_CAM_PIN_D6 17
#define BOARD_CAM_PIN_D7 16
#define BOARD_CAM_PIN_VSYNC 6
#define BOARD_CAM_PIN_HREF 7
#define BOARD_CAM_PIN_PCLK 13

/* PWM into the RC filter and PAM8403. Free of camera, SD (38-40), RGB LED (48), USB (19/20). */
#define BOARD_AUDIO_GPIO 14

/* No battery sense on this board. */
static inline int board_battery_mv(void)
{
    return 0;
}
