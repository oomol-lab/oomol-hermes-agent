ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.6-python3.11-trixie

FROM ${UV_IMAGE}

ARG HERMES_REPOSITORY=https://github.com/NousResearch/hermes-agent.git
ARG HERMES_COMMIT=df4b65147d7ddd74dd449f9067aabbca5aef0ec7
ARG HERMES_VERSION=0.20.2
ARG OO_CLI_VERSION=1.7.4
ARG OO_CLI_SHA256_AMD64=37595b2d8e4cc2c333524442f2b2400191a00bdf993d0925ee2fba11c6687fef
ARG OO_CLI_SHA256_ARM64=6c1f8ae4fc65547288b2ef58a423212aa5709bd9cf075366bfeaa6be00bfd3dd
ARG TARGETARCH
ARG IMAGE_VERSION=dev
ARG IMAGE_REVISION=unknown
ARG IMAGE_SOURCE=https://github.com/oomol/oomol-hermes-agent

LABEL org.opencontainers.image.title="OOMOL Hermes Agent" \
      org.opencontainers.image.description="Hermes Agent Docker distribution with OO CLI, curated Skills, and OOMOL providers" \
      org.opencontainers.image.version="${IMAGE_VERSION}" \
      org.opencontainers.image.revision="${IMAGE_REVISION}" \
      org.opencontainers.image.source="${IMAGE_SOURCE}" \
      org.opencontainers.image.vendor="OOMOL" \
      org.opencontainers.image.licenses="MIT" \
      com.oomol.hermes.version="${HERMES_VERSION}" \
      com.oomol.oo-cli.version="${OO_CLI_VERSION}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl ffmpeg file git jq less nodejs openssh-client ripgrep \
    fonts-dejavu-core fonts-liberation fonts-noto-cjk fonts-wqy-zenhei \
    libreoffice-calc libreoffice-impress libreoffice-writer pandoc \
    poppler-data poppler-utils qpdf \
    gcc g++ libffi-dev make \
    && rm -rf /var/lib/apt/lists/*

RUN node --version

WORKDIR /opt/hermes
RUN git init . \
    && git remote add upstream "${HERMES_REPOSITORY}" \
    && for attempt in 1 2 3; do \
        timeout 600s git \
            -c http.version=HTTP/1.1 \
            -c http.lowSpeedLimit=128 \
            -c http.lowSpeedTime=120 \
            fetch --depth 1 upstream "${HERMES_COMMIT}" \
            && break; \
        if [ "${attempt}" -eq 3 ]; then exit 1; fi; \
        sleep "$((attempt * 5))"; \
    done \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${HERMES_COMMIT}" \
    && test "$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')" = "${HERMES_VERSION}"

COPY patches/0001-skill-description-opt-in.patch /tmp/hermes-patches/
RUN git apply --check /tmp/hermes-patches/0001-skill-description-opt-in.patch \
    && git apply /tmp/hermes-patches/0001-skill-description-opt-in.patch

RUN uv sync --frozen --extra messaging \
    && test -x /opt/hermes/.venv/bin/python

RUN set -eu; \
    case "${TARGETARCH}" in \
        amd64) oo_platform=x64; oo_sha256="${OO_CLI_SHA256_AMD64}" ;; \
        arm64) oo_platform=arm64; oo_sha256="${OO_CLI_SHA256_ARM64}" ;; \
        *) echo "unsupported OO CLI architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --retry 3 \
        "https://static.oomol.com/release/apps/oo-cli/${OO_CLI_VERSION}/linux-${oo_platform}/oo" \
        -o /usr/local/bin/oo; \
    echo "${oo_sha256}  /usr/local/bin/oo" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/oo; \
    oo --version

COPY plugins/image_gen/ /opt/hermes/plugins/image_gen/
COPY plugins/video_gen/ /opt/hermes/plugins/video_gen/
COPY plugins/web/ /opt/hermes/plugins/web/
COPY skills/ /opt/oomol-hermes-agent/skills/
COPY config/ /opt/oomol-hermes-agent/config/
COPY scripts/ /opt/oomol-hermes-agent/scripts/

RUN uv pip install --python /opt/hermes/.venv/bin/python \
        --requirements /opt/oomol-hermes-agent/config/office-python-requirements.txt \
        --requirements /opt/oomol-hermes-agent/config/pdf-python-requirements.txt \
    && python /opt/oomol-hermes-agent/scripts/assemble-skills.py \
        --source /opt/hermes/skills \
        --allowlist /opt/oomol-hermes-agent/config/hermes-skills.txt \
        --additional-source /opt/oomol-hermes-agent/skills \
        --additional-allowlist /opt/oomol-hermes-agent/config/curated-skills.txt \
        --output /opt/oomol-hermes-agent/curated-skills \
    && mkdir -p /opt/oomol-hermes-agent/oo-skills \
    && OO_SKILLS_SYNC_DISABLED=true oo skills install \
        --out-dir /opt/oomol-hermes-agent/oo-skills \
        --agent-format hermes \
    && /opt/hermes/.venv/bin/python /opt/oomol-hermes-agent/scripts/configure-oo-skills.py \
        --skills-dir /opt/oomol-hermes-agent/oo-skills \
    && test -f /opt/oomol-hermes-agent/oo-skills/oo/SKILL.md \
    && node --check /opt/oomol-hermes-agent/curated-skills/research/public-social-research/scripts/tikhub.mjs \
    && python -m compileall -q /opt/hermes/plugins/image_gen/oo_gpt_image_2 \
        /opt/hermes/plugins/image_gen/oo_nano_banana \
        /opt/hermes/plugins/video_gen/oo_seedance \
        /opt/hermes/plugins/web/oo_jina \
    && /opt/hermes/.venv/bin/python /opt/oomol-hermes-agent/scripts/verify-document-runtime.py

ARG HERMES_UID=10000
ARG HERMES_GID=10000
RUN groupadd --gid "${HERMES_GID}" hermes \
    && useradd --uid "${HERMES_UID}" --gid hermes \
        --home-dir /data --create-home --shell /bin/bash hermes \
    && mkdir -p /data/.hermes /data/.config/oo /data/workspace \
    && chown -R hermes:hermes /data \
    && chmod 0755 /opt/oomol-hermes-agent/scripts/entrypoint.sh

ENV HOME=/data \
    HERMES_HOME=/data/.hermes \
    HERMES_BUNDLED_SKILLS=/opt/oomol-hermes-agent/curated-skills \
    OO_CONFIG_DIR=/data/.config/oo \
    OO_SKILLS_SYNC_DISABLED=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/hermes/.venv/bin:/usr/local/bin:/usr/bin:/bin

USER hermes
WORKDIR /data/workspace
VOLUME ["/data"]
EXPOSE 8766

ENTRYPOINT ["/opt/oomol-hermes-agent/scripts/entrypoint.sh"]
CMD ["hermes"]
