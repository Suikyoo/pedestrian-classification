#include "camera.h"

#include "board.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "camera";
static SemaphoreHandle_t s_lock;

static framesize_t to_framesize(devcfg_frame_t f)
{
    switch (f) {
    case DEVCFG_FRAME_QVGA: return FRAMESIZE_QVGA;
    case DEVCFG_FRAME_SVGA: return FRAMESIZE_SVGA;
    case DEVCFG_FRAME_XGA: return FRAMESIZE_XGA;
    case DEVCFG_FRAME_HD: return FRAMESIZE_HD;
    case DEVCFG_FRAME_SXGA: return FRAMESIZE_SXGA;
    case DEVCFG_FRAME_UXGA: return FRAMESIZE_UXGA;
    case DEVCFG_FRAME_VGA:
    default: return FRAMESIZE_VGA;
    }
}

static esp_err_t init_locked(const devcfg_t *c)
{
    camera_config_t cfg = {
        .pin_pwdn = BOARD_CAM_PIN_PWDN,
        .pin_reset = BOARD_CAM_PIN_RESET,
        .pin_xclk = BOARD_CAM_PIN_XCLK,
        .pin_sccb_sda = BOARD_CAM_PIN_SIOD,
        .pin_sccb_scl = BOARD_CAM_PIN_SIOC,
        .pin_d7 = BOARD_CAM_PIN_D7,
        .pin_d6 = BOARD_CAM_PIN_D6,
        .pin_d5 = BOARD_CAM_PIN_D5,
        .pin_d4 = BOARD_CAM_PIN_D4,
        .pin_d3 = BOARD_CAM_PIN_D3,
        .pin_d2 = BOARD_CAM_PIN_D2,
        .pin_d1 = BOARD_CAM_PIN_D1,
        .pin_d0 = BOARD_CAM_PIN_D0,
        .pin_vsync = BOARD_CAM_PIN_VSYNC,
        .pin_href = BOARD_CAM_PIN_HREF,
        .pin_pclk = BOARD_CAM_PIN_PCLK,
        .xclk_freq_hz = 20000000,
        .ledc_timer = LEDC_TIMER_0,     /* audio uses LEDC_TIMER_1 / LEDC_CHANNEL_1 */
        .ledc_channel = LEDC_CHANNEL_0,
        .pixel_format = PIXFORMAT_JPEG,
        /* Allocate buffers for the largest size so frame_size can grow at runtime. */
        .frame_size = FRAMESIZE_UXGA,
        .jpeg_quality = c->jpeg_quality,
        .fb_count = 2,
        .fb_location = CAMERA_FB_IN_PSRAM,
        .grab_mode = CAMERA_GRAB_LATEST,
    };
    esp_err_t err = esp_camera_init(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "init failed: %s", esp_err_to_name(err));
        return err;
    }
    sensor_t *s = esp_camera_sensor_get();
    s->set_framesize(s, to_framesize(c->frame_size));
    s->set_quality(s, c->jpeg_quality);
    return ESP_OK;
}

esp_err_t camera_init(const devcfg_t *c)
{
    s_lock = xSemaphoreCreateMutex();
    xSemaphoreTake(s_lock, portMAX_DELAY);
    esp_err_t err = init_locked(c);
    xSemaphoreGive(s_lock);
    return err;
}

esp_err_t camera_apply(const devcfg_t *c)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    sensor_t *s = esp_camera_sensor_get();
    esp_err_t err = ESP_FAIL;
    if (s != NULL) {
        int a = s->set_framesize(s, to_framesize(c->frame_size));
        int b = s->set_quality(s, c->jpeg_quality);
        err = (a == 0 && b == 0) ? ESP_OK : ESP_FAIL;
    }
    xSemaphoreGive(s_lock);
    return err;
}

esp_err_t camera_reinit(const devcfg_t *c)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    esp_camera_deinit();
    esp_err_t err = init_locked(c);
    xSemaphoreGive(s_lock);
    return err;
}

camera_fb_t *camera_capture(void)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb == NULL) {
        xSemaphoreGive(s_lock);
    }
    return fb; /* lock is held until camera_return */
}

void camera_return(camera_fb_t *fb)
{
    esp_camera_fb_return(fb);
    xSemaphoreGive(s_lock);
}
