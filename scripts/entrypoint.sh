#!/bin/sh
set -eu

mkdir -p "${HERMES_HOME}" "${OO_CONFIG_DIR}" /data/workspace

config_path="${HERMES_HOME}/config.yaml"
if [ ! -e "${config_path}" ]; then
    cp /opt/oomol-hermes-agent/config/config.seed.yaml "${config_path}"
fi

if [ "$#" -eq 0 ]; then
    set -- hermes
fi

exec "$@"
