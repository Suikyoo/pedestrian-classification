#include <stdio.h>

#include "minitest.h"

int mt_checks;
int mt_failures;

void test_backoff(void);

int main(void)
{
    test_backoff();
    printf("%d checks, %d failures\n", mt_checks, mt_failures);
    return mt_failures ? 1 : 0;
}
