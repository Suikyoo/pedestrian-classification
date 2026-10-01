# Pure C, no ESP-IDF headers. Also compiled on the host by test/host/run.sh.
# cJSON comes from the IDF "json" component (ESP-IDF 5.x). On ESP-IDF 6+,
# replace "json" with the managed component espressif/cjson.
idf_component_register(SRCS "backoff.c" "proto.c" "devcfg.c" "msg.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES json)
