#!/bin/sh
set -eu

if [ -z "${OO_API_KEY:-}" ]; then
    echo "error: OO_API_KEY is required" >&2
    exit 64
fi
if [ -z "${OO_LLM_MODEL:-}" ]; then
    echo "error: OO_LLM_MODEL is required" >&2
    exit 64
fi
if [ -z "${OO_LLM_API_MODE:-}" ]; then
    echo "error: OO_LLM_API_MODE is required" >&2
    exit 64
fi
if [ -z "${OO_LLM_BASE_URL:-}" ]; then
    echo "error: OO_LLM_BASE_URL is required" >&2
    exit 64
fi

case "${OO_LLM_API_MODE}" in
    chat_completions|codex_responses) ;;
    *)
        echo "error: OO_LLM_API_MODE must be chat_completions or codex_responses" >&2
        exit 64
        ;;
esac

case "${OO_LLM_BASE_URL}" in
    https://*/v1|https://*/v1/) ;;
    *)
        echo "error: OO_LLM_BASE_URL must be an HTTPS base URL ending in /v1" >&2
        exit 64
        ;;
esac

normalized_base_url="${OO_LLM_BASE_URL%/}"
base_authority_and_path="${normalized_base_url#https://}"
base_authority="${base_authority_and_path%%/*}"
case "${normalized_base_url}" in
    *'?'*|*'#'*)
        echo "error: OO_LLM_BASE_URL must not contain a query or fragment" >&2
        exit 64
        ;;
esac
case "${base_authority}" in
    ''|*'@'*)
        echo "error: OO_LLM_BASE_URL must contain a safe hostname" >&2
        exit 64
        ;;
esac

mkdir -p "${HERMES_HOME}" "${OO_CONFIG_DIR}" /data/workspace

# Intentional deployment tradeoff: terminal processes cannot receive
# OO_API_KEY, so publish a saved oo-cli account from a private staging dir.
# A failed refresh removes the old account rather than using stale credentials.
auth_staging_dir="$(mktemp -d "${OO_CONFIG_DIR}/.auth-login.XXXXXX")"
if OO_CONFIG_DIR="${auth_staging_dir}" \
    timeout 30 oo auth login --api-key "${OO_API_KEY}" >/dev/null 2>&1 \
    && [ -s "${auth_staging_dir}/auth.toml" ]; then
    chmod 0600 "${auth_staging_dir}/auth.toml"
    mv -f "${auth_staging_dir}/auth.toml" "${OO_CONFIG_DIR}/auth.toml"
else
    rm -f "${OO_CONFIG_DIR}/auth.toml"
    echo "warning: could not persist oo-cli authentication; continuing without terminal OO access" >&2
fi
rm -rf "${auth_staging_dir}"

config_path="${HERMES_HOME}/config.yaml"
if [ ! -e "${config_path}" ]; then
    cp /opt/oomol-hermes-agent/config/config.seed.yaml "${config_path}"
fi
/opt/hermes/.venv/bin/python \
    /opt/oomol-hermes-agent/scripts/materialize-config-env.py "${config_path}"

if [ "$#" -eq 0 ]; then
    set -- hermes
fi

exec "$@"
