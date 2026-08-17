#!/bin/sh
set -eu

repo_root="${REPO_ROOT:-$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)}"
event_name="${RELEASE_EVENT_NAME:-${GITHUB_EVENT_NAME:-}}"
default_branch="${RELEASE_BRANCH:-main}"
dispatch_sha="${RELEASE_DISPATCH_SHA:-${GITHUB_SHA:-}}"
today="${PREPARE_RELEASE_TODAY:-$(date -u +%Y.%m.%d)}"
dry_run=0
push=0
explicit_tag=""
reuse_tag=""

fail() {
    printf 'prepare-release: %s\n' "$1" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: scripts/prepare-release.sh [options]

Prepare an immutable image release tag. The release version is an annotated
Git tag; no version file or release-only source commit is created.

Options:
  --dry-run         Print the planned release without creating a tag.
  --push            Push a newly-created tag to origin.
  --tag VALUE       Use an explicit tag instead of today's next tag.
  --reuse-tag VALUE Validate and reuse an existing immutable release tag.
  -h, --help        Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) dry_run=1 ;;
        --push) push=1 ;;
        --tag)
            [ "$#" -ge 2 ] || fail "--tag requires a value"
            explicit_tag="$2"
            shift
            ;;
        --reuse-tag)
            [ "$#" -ge 2 ] || fail "--reuse-tag requires a value"
            reuse_tag="$2"
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option: $1" ;;
    esac
    shift
done

[ -z "$explicit_tag" ] || [ -z "$reuse_tag" ] \
    || fail "--tag and --reuse-tag are mutually exclusive"
[ -z "$reuse_tag" ] || [ "$push" = "0" ] \
    || fail "--push cannot be used with --reuse-tag"

command -v git >/dev/null 2>&1 || fail "missing required command: git"
command -v python3 >/dev/null 2>&1 || fail "missing required command: python3"

validate_tag() {
    python3 - "$1" <<'PY' \
        || fail "release tag must look like vYYYY.MM.DD-N, got: $1"
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

read_lock_metadata() {
    hermes_commit="$(read_lock_field hermes.commit)"
    hermes_version="$(read_lock_field hermes.version)"
    oo_cli_version="$(read_lock_field oo_cli.version)"
    oo_cli_sha256_amd64="$(read_lock_field oo_cli.artifacts.linux-amd64.sha256)"
    oo_cli_sha256_arm64="$(read_lock_field oo_cli.artifacts.linux-arm64.sha256)"
}

read_tag_metadata() {
    tag_type="$(git -C "$repo_root" cat-file -t "$release_tag" 2>/dev/null || true)"
    [ "$tag_type" = "tag" ] || fail "release tag must be annotated: ${release_tag}"
    tag_contents="$(git -C "$repo_root" for-each-ref \
        --format='%(contents)' "refs/tags/${release_tag}")"
    hermes_commit="$(printf '%s\n' "$tag_contents" | sed -n 's/^HERMES_COMMIT=//p' | head -n 1)"
    hermes_version="$(printf '%s\n' "$tag_contents" | sed -n 's/^HERMES_VERSION=//p' | head -n 1)"
    oo_cli_version="$(printf '%s\n' "$tag_contents" | sed -n 's/^OO_CLI_VERSION=//p' | head -n 1)"
    oo_cli_sha256_amd64="$(printf '%s\n' "$tag_contents" | sed -n 's/^OO_CLI_SHA256_AMD64=//p' | head -n 1)"
    oo_cli_sha256_arm64="$(printf '%s\n' "$tag_contents" | sed -n 's/^OO_CLI_SHA256_ARM64=//p' | head -n 1)"
    [ -n "$hermes_commit" ] || fail "release tag is missing HERMES_COMMIT: ${release_tag}"
    [ -n "$hermes_version" ] || fail "release tag is missing HERMES_VERSION: ${release_tag}"
    [ -n "$oo_cli_version" ] || fail "release tag is missing OO_CLI_VERSION: ${release_tag}"
    [ -n "$oo_cli_sha256_amd64" ] \
        || fail "release tag is missing OO_CLI_SHA256_AMD64: ${release_tag}"
    [ -n "$oo_cli_sha256_arm64" ] \
        || fail "release tag is missing OO_CLI_SHA256_ARM64: ${release_tag}"
}

next_tag() {
    tags="$(git -C "$repo_root" tag -l "v${today}-*")"
    python3 - "$today" "$tags" <<'PY'
import re
import sys

today, raw_tags = sys.argv[1:]
pattern = re.compile(r"^v(\d{4}\.\d{2}\.\d{2})-(\d+)$")
suffixes = []
for raw_tag in raw_tags.splitlines():
    match = pattern.fullmatch(raw_tag.strip())
    if match and match.group(1) == today:
        suffixes.append(int(match.group(2)))
print(f"v{today}-{max(suffixes, default=0) + 1}")
PY
}

if [ "$event_name" != "push" ] && [ "${GITHUB_REF_TYPE:-}" != "tag" ]; then
    if [ "${PREPARE_RELEASE_SKIP_GIT_CLEAN_CHECK:-0}" != "1" ]; then
        git -C "$repo_root" diff --quiet \
            || fail "working tree has unstaged changes"
        git -C "$repo_root" diff --cached --quiet \
            || fail "working tree has staged changes"
        untracked="$(git -C "$repo_root" ls-files --others --exclude-standard)"
        [ -z "$untracked" ] || fail "working tree has untracked files"
    fi
    if [ "${PREPARE_RELEASE_SKIP_FETCH_TAGS:-0}" != "1" ] \
            && git -C "$repo_root" remote get-url origin >/dev/null 2>&1; then
        git -C "$repo_root" fetch --tags --quiet origin
    fi
fi

if [ -n "$reuse_tag" ]; then
    release_tag="$reuse_tag"
elif [ -n "$explicit_tag" ]; then
    release_tag="$explicit_tag"
elif [ "$event_name" = "push" ] || [ "${GITHUB_REF_TYPE:-}" = "tag" ]; then
    release_tag="${GITHUB_REF_NAME:-}"
    [ -n "$release_tag" ] || fail "GITHUB_REF_NAME is required for a tag release"
else
    release_tag="$(next_tag)"
fi
validate_tag "$release_tag"

if [ -n "${GITHUB_REF_NAME:-}" ] && [ "$event_name" = "workflow_dispatch" ] \
        && [ "$GITHUB_REF_NAME" != "$default_branch" ]; then
    fail "workflow_dispatch must run from ${default_branch}, got ${GITHUB_REF_NAME}"
fi

if [ -n "$reuse_tag" ] || [ "$event_name" = "push" ] \
        || [ "${GITHUB_REF_TYPE:-}" = "tag" ]; then
    source_commit="$(git -C "$repo_root" rev-list -n 1 "${release_tag}^{commit}")" \
        || fail "tag does not resolve: ${release_tag}"
    read_tag_metadata
else
    source_commit="$dispatch_sha"
    [ -n "$source_commit" ] || source_commit="$(git -C "$repo_root" rev-parse HEAD)"
    git -C "$repo_root" cat-file -e "${source_commit}^{commit}" 2>/dev/null \
        || fail "source commit does not exist: ${source_commit}"
    read_lock_metadata
fi

if [ "$dry_run" = "1" ]; then
    printf 'release tag: %s\n' "$release_tag"
    printf 'source commit: %s\n' "$source_commit"
    printf 'Hermes version: %s\n' "$hermes_version"
    printf 'OO CLI version: %s\n' "$oo_cli_version"
    exit 0
fi

if [ -n "$reuse_tag" ] || [ "$event_name" = "push" ] \
        || [ "${GITHUB_REF_TYPE:-}" = "tag" ]; then
    existing_commit="$(git -C "$repo_root" rev-list -n 1 "${release_tag}^{commit}")"
    [ "$existing_commit" = "$source_commit" ] \
        || fail "existing tag points to a different commit: ${release_tag}"
else
    git -C "$repo_root" show-ref --verify --quiet "refs/tags/${release_tag}" \
        && fail "release tag already exists: ${release_tag}"
    tag_message="$(mktemp)"
    trap 'rm -f "$tag_message"' EXIT HUP INT TERM
    {
        printf 'Release %s\n\n' "$release_tag"
        printf 'HERMES_COMMIT=%s\n' "$hermes_commit"
        printf 'HERMES_VERSION=%s\n' "$hermes_version"
        printf 'OO_CLI_VERSION=%s\n' "$oo_cli_version"
        printf 'OO_CLI_SHA256_AMD64=%s\n' "$oo_cli_sha256_amd64"
        printf 'OO_CLI_SHA256_ARM64=%s\n' "$oo_cli_sha256_arm64"
    } > "$tag_message"
    git -C "$repo_root" tag -a "$release_tag" "$source_commit" -F "$tag_message"
    if [ "$push" = "1" ]; then
        git -C "$repo_root" push origin "$release_tag"
    fi
fi

if [ -n "${GITHUB_OUTPUT:-}" ]; then
    {
        printf 'release_tag=%s\n' "$release_tag"
        printf 'source_commit=%s\n' "$source_commit"
    } >> "$GITHUB_OUTPUT"
fi

printf 'prepare-release: %s at %s\n' "$release_tag" "$source_commit"
