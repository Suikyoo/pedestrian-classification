#pragma once
#include "core/devcfg.h"
#include "esp_camera.h"
#include "esp_err.h"

/* Thread-safe wrapper: capture and reconfiguration never overlap. */
esp_err_t camera_init(const devcfg_t *c);
esp_err_t camera_apply(const devcfg_t *c);  /* frame size + JPEG quality */
esp_err_t camera_reinit(const devcfg_t *c); /* deinit + init, after repeated failures */
camera_fb_t *camera_capture(void);          /* NULL on failure; pair with camera_return */
void camera_return(camera_fb_t *fb);
