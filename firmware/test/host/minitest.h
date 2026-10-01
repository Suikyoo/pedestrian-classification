#pragma once
#include <stdio.h>
#include <string.h>

extern int mt_checks;
extern int mt_failures;

#define CHECK(cond)                                                          \
    do {                                                                     \
        mt_checks++;                                                         \
        if (!(cond)) {                                                       \
            mt_failures++;                                                   \
            printf("%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond);  \
        }                                                                    \
    } while (0)

#define CHECK_INT(actual, expected)                                          \
    do {                                                                     \
        long long a_ = (long long)(actual), e_ = (long long)(expected);      \
        mt_checks++;                                                         \
        if (a_ != e_) {                                                      \
            mt_failures++;                                                   \
            printf("%s:%d: %s == %lld, expected %lld\n", __FILE__, __LINE__, \
                   #actual, a_, e_);                                         \
        }                                                                    \
    } while (0)

#define CHECK_STR(actual, expected)                                          \
    do {                                                                     \
        const char *a_ = (actual), *e_ = (expected);                         \
        mt_checks++;                                                         \
        if (a_ == NULL || strcmp(a_, e_) != 0) {                             \
            mt_failures++;                                                   \
            printf("%s:%d: %s == \"%s\", expected \"%s\"\n", __FILE__,       \
                   __LINE__, #actual, a_ ? a_ : "(null)", e_);               \
        }                                                                    \
    } while (0)
