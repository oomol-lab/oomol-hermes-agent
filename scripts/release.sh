#!/bin/sh
set -eu

repo_root="${REPO_ROOT:-$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)}"
release_tag="${RELEASE_TAG:-${GITHUB_REF_NAME:-}}"
commit_sha="${RELEASE_COMMIT_SHA:-${GITHUB_SHA:-}}"
image_repository="${IMAGE_REPOSITORY:-}"
image_source="${IMAGE_SOURCE:-https://github.com/oomol-lab/oomol-hermes-agent}"
platforms="${RELEASE_PLATFORMS:-linux/amd64,linux/arm64}"
dry_run="${DRY_RUN:-0}"
publish_latest="${PUBLISH_LATEST:-1}"

fail() {
    printf 'release: %s\n' "$1" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

validate_tag() {
    python3 - "$1" <<'PY' \
        || fail "RELEASE_TAG must look like vYYYY.MM.DD-N, got: $1"
import re
import sys

raise SystemExit(
    0 if re.fullmatch(r"v\d{4}\.\d{2}\.\d{2}-[1-9]\d*", sys.argv[1]) else 1
)
PY
}

read_lock_field() {
    python3 - "$repo_root/upstream.lock.json" "$1" <<'PY'
import json
import sys

path, dotted_key = sys.argv[1:]
with open(path, encoding="utf-8") as source:
    value = json.load(source)
for key in dotted_key.split("."):
    value = value[key]
if not isinstance(value, (str, int)):
    raise SystemExit(f"release metadata is not scalar: {dotted_key}")
print(value)
PY
}

tag_field() {
    printf '%s\n' "$tag_contents" | sed -n "s/^$1=//p" | head -n 1
}

require_command git
require_command python3
[ -n "$release_tag" ] || fail "RELEASE_TAG is required"
validate_tag "$release_tag"
[ -n "$image_repository" ] || fail "IMAGE_REPOSITORY is required"

if [ -z "$commit_sha" ]; then
    commit_sha="$(git -C "$repo_root" rev-parse "${release_tag}^{commit}")"
fi
git -C "$repo_root" cat-file -e "${commit_sha}^{commit}" 2>/dev/null \
    || fail "source commit does not exist: ${commit_sha}"
tag_commit="$(git -C "$repo_root" rev-list -n 1 "${release_tag}^{commit}")" \
    || fail "release tag does not resolve: ${release_tag}"
[ "$tag_commit" = "$commit_sha" ] \
    || fail "release tag ${release_tag} does not point to ${commit_sha}"
tag_type="$(git -C "$repo_root" cat-file -t "$release_tag" 2>/dev/null || true)"
[ "$tag_type" = "tag" ] || fail "release tag must be annotated: ${release_tag}"

hermes_commit="$(read_lock_field hermes.commit)"
hermes_version="$(read_lock_field hermes.version)"
oo_cli_version="$(read_lock_field oo_cli.version)"
oo_cli_sha256_amd64="$(read_lock_field oo_cli.artifacts.linux-amd64.sha256)"
oo_cli_sha256_arm64="$(read_lock_field oo_cli.artifacts.linux-arm64.sha256)"
tag_contents="$(git -C "$repo_root" for-each-ref \
    --format='%(contents)' "refs/tags/${release_tag}")"

for metadata_name in HERMES_COMMIT HERMES_VERSION OO_CLI_VERSION \
        OO_CLI_SHA256_AMD64 OO_CLI_SHA256_ARM64; do
    case "$metadata_name" in
        HERMES_COMMIT) expected="$hermes_commit" ;;
        HERMES_VERSION) expected="$hermes_version" ;;
        OO_CLI_VERSION) expected="$oo_cli_version" ;;
        OO_CLI_SHA256_AMD64) expected="$oo_cli_sha256_amd64" ;;
        OO_CLI_SHA256_ARM64) expected="$oo_cli_sha256_arm64" ;;
    esac
    actual="$(tag_field "$metadata_name")"
    [ "$actual" = "$expected" ] \
        || fail "${metadata_name} in ${release_tag} does not match upstream.lock.json"
done

created="$(git -C "$repo_root" show -s --format=%cI "$commit_sha")"
version_image="${image_repository}:${release_tag}"
sha_image="${image_repository}:${commit_sha}"
latest_image="${image_repository}:latest"

printf 'release image: %s\n' "$version_image"
printf 'source commit: %s\n' "$commit_sha"
printf 'Hermes version: %s\n' "$hermes_version"
printf 'OO CLI version: %s\n' "$oo_cli_version"
printf 'platforms: %s\n' "$platforms"

if [ "$dry_run" = "1" ]; then
    printf 'release: dry run complete\n'
    exit 0
fi

require_command docker

set -- docker buildx build \
    --file "$repo_root/Dockerfile" \
    --platform "$platforms" \
    --provenance=mode=max \
    --sbom=true \
    --build-arg "IMAGE_VERSION=${release_tag}" \
    --build-arg "IMAGE_REVISION=${commit_sha}" \
    --build-arg "IMAGE_SOURCE=${image_source}" \
    --build-arg "IMAGE_CREATED=${created}" \
    --build-arg "HERMES_COMMIT=${hermes_commit}" \
    --build-arg "HERMES_VERSION=${hermes_version}" \
    --build-arg "OO_CLI_VERSION=${oo_cli_version}" \
    --build-arg "OO_CLI_SHA256_AMD64=${oo_cli_sha256_amd64}" \
    --build-arg "OO_CLI_SHA256_ARM64=${oo_cli_sha256_arm64}" \
    --tag "$version_image" \
    --tag "$sha_image"

case "$publish_latest" in
    1|true|TRUE|yes|YES) set -- "$@" --tag "$latest_image" ;;
    0|false|FALSE|no|NO) ;;
    *) fail "PUBLISH_LATEST must be true or false, got: $publish_latest" ;;
esac

if [ -n "${DOCKER_CACHE_FROM:-}" ]; then
    set -- "$@" --cache-from "$DOCKER_CACHE_FROM"
fi
if [ -n "${DOCKER_CACHE_TO:-}" ]; then
    set -- "$@" --cache-to "$DOCKER_CACHE_TO"
fi

set -- "$@" --push "$repo_root"
"$@"

image_digest() {
    image="$1"
    raw="$(docker buildx imagetools inspect "$image" --format '{{json .}}')" \
        || fail "could not inspect ${image}"
    printf '%s' "$raw" | python3 -c '
import json
import sys

data = json.load(sys.stdin)
manifest = data.get("manifest") or data.get("Manifest") or {}
digest = manifest.get("digest") or manifest.get("Digest")
if not digest:
    raise SystemExit("registry manifest digest is missing")
print(digest)
'
}

version_digest="$(image_digest "$version_image")"
sha_digest="$(image_digest "$sha_image")"
[ "$version_digest" = "$sha_digest" ] \
    || fail "version/SHA digest mismatch: ${version_digest} != ${sha_digest}"

case "$publish_latest" in
    1|true|TRUE|yes|YES)
        latest_digest="$(image_digest "$latest_image")"
        [ "$version_digest" = "$latest_digest" ] \
            || fail "version/latest digest mismatch: ${version_digest} != ${latest_digest}"
        ;;
esac

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
        printf '## OOMOL Hermes Agent image release\n\n'
        printf '| Field | Value |\n| --- | --- |\n'
        printf "| Image version | \`%s\` |\n" "$release_tag"
        printf "| Source commit | \`%s\` |\n" "$commit_sha"
        printf "| Hermes version | \`%s\` |\n" "$hermes_version"
        printf "| OO CLI version | \`%s\` |\n" "$oo_cli_version"
        printf "| Image | \`%s\` |\n" "$version_image"
        printf "| Digest | \`%s\` |\n" "$version_digest"
    } >> "$GITHUB_STEP_SUMMARY"
fi

if [ -n "${GITHUB_ENV:-}" ]; then
    {
        printf 'RELEASE_IMAGE=%s\n' "$version_image"
        printf 'RELEASE_IMAGE_DIGEST=%s\n' "$version_digest"
        printf 'RELEASE_HERMES_VERSION=%s\n' "$hermes_version"
        printf 'RELEASE_OO_CLI_VERSION=%s\n' "$oo_cli_version"
    } >> "$GITHUB_ENV"
fi

if [ -n "${GITHUB_OUTPUT:-}" ]; then
    {
        printf 'release_image=%s\n' "$version_image"
        printf 'release_digest=%s\n' "$version_digest"
    } >> "$GITHUB_OUTPUT"
fi

printf 'release: verified digest %s\n' "$version_digest"
