#include "audio.h"

#include "board.h"
#include "core/pcm.h"
#include "driver/gptimer.h"
#include "driver/ledc.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"

static const char *TAG = "audio";

#define AUDIO_LEDC_TIMER LEDC_TIMER_1     /* camera XCLK uses LEDC_TIMER_0 */
#define AUDIO_LEDC_CHANNEL LEDC_CHANNEL_1
#define AUDIO_PWM_HZ 78000
#define AUDIO_SAMPLE_HZ 16000
#define AUDIO_SILENCE 128

extern const uint8_t alert_raw_start[] asm("_binary_alert_raw_start");
extern const uint8_t alert_raw_end[] asm("_binary_alert_raw_end");

static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;
static volatile size_t s_pos;
static volatile int s_repeats_left;
static volatile bool s_playing;
static volatile uint8_t s_volume = 80;

static void set_duty(uint32_t duty)
{
    ledc_set_duty(LEDC_LOW_SPEED_MODE, AUDIO_LEDC_CHANNEL, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, AUDIO_LEDC_CHANNEL);
}

static bool on_sample(gptimer_handle_t timer, const gptimer_alarm_event_data_t *e, void *ctx)
{
    int duty = -1; /* -1 = idle, leave the output alone */
    portENTER_CRITICAL_ISR(&s_mux);
    if (s_playing) {
        size_t len = (size_t)(alert_raw_end - alert_raw_start);
        if (s_pos >= len) {
            if (--s_repeats_left > 0) {
                s_pos = 0;
            } else {
                s_playing = false;
            }
        }
        duty = s_playing ? pcm_scale(alert_raw_start[s_pos++], s_volume) : AUDIO_SILENCE;
    }
    portEXIT_CRITICAL_ISR(&s_mux);
    if (duty >= 0) {
        set_duty((uint32_t)duty); /* outside our lock: ledc takes its own */
    }
    return false;
}

esp_err_t audio_init(void)
{
    ledc_timer_config_t t = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_8_BIT,
        .timer_num = AUDIO_LEDC_TIMER,
        .freq_hz = AUDIO_PWM_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&t));
    ledc_channel_config_t ch = {
        .gpio_num = BOARD_AUDIO_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = AUDIO_LEDC_CHANNEL,
        .timer_sel = AUDIO_LEDC_TIMER,
        .duty = AUDIO_SILENCE,
        .hpoint = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&ch));

    gptimer_handle_t timer;
    gptimer_config_t tc = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000,
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&tc, &timer));
    gptimer_event_callbacks_t cbs = {.on_alarm = on_sample};
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(timer, &cbs, NULL));
    gptimer_alarm_config_t alarm = {
        .alarm_count = 1000000 / AUDIO_SAMPLE_HZ, /* 62 us -> 16.13 kHz, pitch +0.8% */
        .reload_count = 0,
        .flags.auto_reload_on_alarm = true,
    };
    ESP_ERROR_CHECK(gptimer_set_alarm_action(timer, &alarm));
    ESP_ERROR_CHECK(gptimer_enable(timer));
    ESP_ERROR_CHECK(gptimer_start(timer));
    ESP_LOGI(TAG, "ready: %u-byte clip on GPIO %d", (unsigned)(alert_raw_end - alert_raw_start),
             BOARD_AUDIO_GPIO);
    return ESP_OK;
}

void audio_set_volume(uint8_t volume)
{
    s_volume = volume > 100 ? 100 : volume;
}

void audio_play(int repeat)
{
    portENTER_CRITICAL(&s_mux);
    s_pos = 0;
    s_repeats_left = repeat < 1 ? 1 : repeat;
    s_playing = true;
    portEXIT_CRITICAL(&s_mux);
    ESP_LOGI(TAG, "playing alert x%d", repeat);
}
