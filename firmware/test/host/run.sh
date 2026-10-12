#!/usr/bin/env sh
# Build and run host unit tests for components/core. Needs only a C compiler.
set -e
cd "$(dirname "$0")"
CC="${CC:-gcc}"
mkdir -p build
"$CC" -std=c11 -O1 -Ithird_party -c third_party/cJSON.c -o build/cJSON.o
# 32-bit x86 uses x87 FP with excess precision, which breaks exact float checks; use SSE there.
FPFLAGS=""
case "$("$CC" -dumpmachine)" in i?86*|mingw32) FPFLAGS="-mfpmath=sse -msse2" ;; esac
"$CC" -std=c11 $FPFLAGS -Wall -Wextra -Werror -I../../components/core/include -Ithird_party \
    ../../components/core/*.c test_*.c build/cJSON.o -o build/host_tests
./build/host_tests
