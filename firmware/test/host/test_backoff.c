#include "core/backoff.h"
#include "minitest.h"

void test_backoff(void)
{
    backoff_t b;
    backoff_reset(&b);
    CHECK_INT(backoff_next_ms(&b), 5000);
    CHECK_INT(backoff_next_ms(&b), 10000);
    CHECK_INT(backoff_next_ms(&b), 30000);
    CHECK_INT(backoff_next_ms(&b), 60000);
    CHECK_INT(backoff_next_ms(&b), 60000);
    CHECK_INT(backoff_next_ms(&b), 60000);

    backoff_reset(&b);
    CHECK_INT(backoff_next_ms(&b), 5000);
}
