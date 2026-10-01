#include <stdio.h>

#include "minitest.h"

int mt_checks;
int mt_failures;

void test_backoff(void);
void test_proto(void);

int main(void)
{
    test_backoff();
    test_proto();
    printf("%d checks, %d failures\n", mt_checks, mt_failures);
    return mt_failures ? 1 : 0;
}
