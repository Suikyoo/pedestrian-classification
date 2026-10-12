#include <stdio.h>

#include "minitest.h"

int mt_checks;
int mt_failures;

void test_backoff(void);
void test_proto(void);
void test_devcfg(void);
void test_msg(void);
void test_pcm(void);
void test_dwell(void);

int main(void)
{
    test_backoff();
    test_proto();
    test_devcfg();
    test_msg();
    test_pcm();
    test_dwell();
    printf("%d checks, %d failures\n", mt_checks, mt_failures);
    return mt_failures ? 1 : 0;
}
