#pragma once
#include "sdkconfig.h"

/* The only place that knows which board is in use. Pins live in boards/*.h. */
#if CONFIG_BOARD_FREENOVE_S3CAM
#include "boards/freenove_s3cam.h"
#else
#error "No board selected: menuconfig > Pedestrian Edge > Board"
#endif
