#!/bin/sh
# Builds Mosquitto's password and ACL files from the environment, then starts the broker.
#   MQTT_USER / MQTT_PASS   the server account (master service and CLI): every topic
#   DEVICE_CREDENTIALS      space-separated <device-id>:<password> pairs; a device may
#                           only use topics under its own id ({id}/...)
set -eu
: "${MQTT_USER:?set MQTT_USER in .env}"
: "${MQTT_PASS:?set MQTT_PASS in .env}"
: "${DEVICE_CREDENTIALS:?set DEVICE_CREDENTIALS in .env}"

passwd=/mosquitto/passwd
acl=/mosquitto/acl

rm -f "$passwd"
touch "$passwd"
mosquitto_passwd -b "$passwd" "$MQTT_USER" "$MQTT_PASS"
for cred in $DEVICE_CREDENTIALS; do
    mosquitto_passwd -b "$passwd" "${cred%%:*}" "${cred#*:}"
done

cat > "$acl" <<EOF
user $MQTT_USER
topic readwrite #

pattern readwrite %u/#
EOF

chown mosquitto:mosquitto "$passwd" "$acl"
chmod 0700 "$passwd" "$acl"
exec /usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf
