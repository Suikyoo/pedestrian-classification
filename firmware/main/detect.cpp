// The only C++ file: a C facade over ESP-DL's PedestrianDetect.
#include "detect.h"

#include <cstring>
#include <new>

#include "dl_image_jpeg.hpp"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_partition.h"
#include "esp_timer.h"
#include "pedestrian_detect.hpp"

static const char *TAG = "detect";
// The model drops boxes below its own threshold (0.7 by default). Keep nearly
// all of them so devcfg's threshold decides what counts as a pedestrian.
static constexpr float MODEL_SCORE_FLOOR = 0.05f;
static constexpr int LOG_EVERY = 30; // frames between timing logs

static PedestrianDetect *s_model;
static int s_frames;

esp_err_t detect_init(void)
{
    const esp_partition_t *part =
        esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "pedestrian_det");
    if (part == NULL) {
        ESP_LOGE(TAG, "no pedestrian_det partition; detection disabled");
        return ESP_ERR_NOT_FOUND;
    }
    char magic[5] = {0};
    if (esp_partition_read(part, 0, magic, 4) != ESP_OK ||
        (magic[0] & magic[1] & magic[2] & magic[3] & 0xFF) == 0xFF) {
        ESP_LOGE(TAG, "pedestrian_det partition is empty (run idf.py flash); detection disabled");
        return ESP_ERR_INVALID_STATE;
    }
    // ESP-DL's loader accepts only these format tags at offset 0.
    static const char *const kMagics[] = {"EDL1", "EDL2", "PDL1", "PDL2", "PDL3"};
    bool known = false;
    for (const char *m : kMagics) {
        if (memcmp(magic, m, 4) == 0) {
            known = true;
            break;
        }
    }
    if (!known) {
        ESP_LOGE(TAG, "pedestrian_det does not hold an ESP-DL model (magic %02x%02x%02x%02x); detection disabled",
                 (unsigned)(uint8_t)magic[0], (unsigned)(uint8_t)magic[1], (unsigned)(uint8_t)magic[2],
                 (unsigned)(uint8_t)magic[3]);
        return ESP_ERR_INVALID_VERSION;
    }
    int64_t t0 = esp_timer_get_time();
    s_model = new (std::nothrow) PedestrianDetect(PedestrianDetect::PICO_S8_V1, false);
    if (s_model == NULL) {
        ESP_LOGE(TAG, "out of memory loading the model; detection disabled");
        return ESP_ERR_NO_MEM;
    }
    s_model->set_score_thr(MODEL_SCORE_FLOOR);
    ESP_LOGI(TAG, "model loaded in %d ms", (int)((esp_timer_get_time() - t0) / 1000));
    return ESP_OK;
}

float detect_score(const uint8_t *jpeg, size_t len)
{
    if (s_model == NULL) {
        return -1.0f;
    }
    int64_t t0 = esp_timer_get_time();
    dl::image::jpeg_img_t jpeg_img = {.data = (void *)jpeg, .data_len = len};
    dl::image::img_t img = dl::image::sw_decode_jpeg(jpeg_img, dl::image::DL_IMAGE_PIX_TYPE_RGB888);
    if (img.data == NULL) {
        ESP_LOGW(TAG, "JPEG decode failed (%u bytes)", (unsigned)len);
        return -1.0f;
    }
    int64_t t1 = esp_timer_get_time();
    float best = 0.0f;
    for (const auto &r : s_model->run(img)) {
        if (r.score > best) {
            best = r.score;
        }
    }
    heap_caps_free(img.data);
    if (++s_frames % LOG_EVERY == 1) {
        int64_t t2 = esp_timer_get_time();
        ESP_LOGI(TAG, "%dx%d: decode %d ms, inference %d ms, score %.2f", img.width, img.height,
                 (int)((t1 - t0) / 1000), (int)((t2 - t1) / 1000), best);
    }
    return best > 1.0f ? 1.0f : best;
}
