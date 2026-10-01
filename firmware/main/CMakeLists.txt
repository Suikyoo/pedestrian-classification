set(srcs
    "main.c"
    "config_store.c"
    "timesync.c"
    "mqtt_link.c"
    "cmd.c"
    "camera.c"
    "stream.c"
    "audio.c"
    "status.c")

# Exactly one network backend implements net.h.
if(CONFIG_NET_BACKEND_WIFI)
    list(APPEND srcs "net_wifi.c")
endif()

idf_component_register(SRCS ${srcs}
                       INCLUDE_DIRS "."
                       REQUIRES core driver esp_wifi esp_netif esp_event esp_timer
                                nvs_flash mqtt mbedtls lwip efuse
                       EMBED_FILES "assets/alert.raw")
