#!/usr/bin/env sh
# Build and run host unit tests for components/core. Needs only a C compiler.
set -e
cd "$(dirname "$0")"
CC="${CC:-gcc}"
mkdir -p build
"$CC" -std=c11 -O1 -Ithird_party -c third_party/cJSON.c -o build/cJSON.o
"$CC" -std=c11 -Wall -Wextra -Werror -I../../components/core/include -Ithird_party \
    ../../components/core/*.c test_*.c build/cJSON.o -o build/host_tests
./build/host_tests
