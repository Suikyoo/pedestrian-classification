#include "core/pcm.h"
#include "minitest.h"

void test_pcm(void)
{
    CHECK_INT(pcm_scale(255, 100), 255);
    CHECK_INT(pcm_scale(0, 100), 0);
    CHECK_INT(pcm_scale(128, 100), 128);
    CHECK_INT(pcm_scale(255, 0), 128);
    CHECK_INT(pcm_scale(0, 0), 128);
    CHECK_INT(pcm_scale(255, 50), 191);
    CHECK_INT(pcm_scale(0, 50), 64);
    CHECK_INT(pcm_scale(0, 200), 0); /* volume above 100 is clamped */
}
