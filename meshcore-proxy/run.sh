#!/usr/bin/with-contenv bashio
set -e

SERIAL_PORT=$(bashio::config 'serial_port')
BAUDRATE=$(bashio::config 'baudrate')
LISTEN_PORT=$(bashio::config 'listen_port')
QUIET_RELEASE=$(bashio::config 'turn_quiet_seconds')
MAX_HOLD=$(bashio::config 'turn_max_seconds')
LOG_LEVEL=$(bashio::config 'log_level')

if [ ! -e "${SERIAL_PORT}" ]; then
    bashio::log.fatal "Serial port ${SERIAL_PORT} does not exist."
    bashio::log.fatal "Plug in the radio and check the 'serial_port' option (a /dev/serial/by-id/... path is the most stable)."
    ls -l /dev/serial/by-id/ 2>/dev/null || true
    exit 1
fi

bashio::log.info "Starting meshcore-proxy: ${SERIAL_PORT} @ ${BAUDRATE} -> 0.0.0.0:${LISTEN_PORT}"
exec python3 /opt/proxy.py \
    --serial-port "${SERIAL_PORT}" \
    --baudrate "${BAUDRATE}" \
    --listen-host 0.0.0.0 \
    --listen-port "${LISTEN_PORT}" \
    --quiet-release "${QUIET_RELEASE}" \
    --max-hold "${MAX_HOLD}" \
    --log-level "${LOG_LEVEL}"
