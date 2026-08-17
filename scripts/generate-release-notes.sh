#!/bin/sh
set -eu

repo_root="${REPO_ROOT:-$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)}"

require_value() {
    eval "value=\${$1:-}"
    [ -n "$value" ] || {
        printf 'generate-release-notes: %s is required\n' "$1" >&2
        exit 1
    }
}

require_value RELEASE_TAG
require_value RELEASE_COMMIT_SHA
require_value RELEASE_IMAGE
require_value RELEASE_IMAGE_DIGEST
require_value RELEASE_HERMES_VERSION
require_value RELEASE_OO_CLI_VERSION
require_value IMAGE_REPOSITORY

release_summary_file="${RELEASE_SUMMARY_FILE:-}"
if [ -n "$release_summary_file" ]; then
    : > "$release_summary_file" || {
        printf 'generate-release-notes: could not write RELEASE_SUMMARY_FILE\n' >&2
        exit 1
    }
fi

release_tags="$(git -C "$repo_root" for-each-ref \
    --merged="$RELEASE_COMMIT_SHA" \
    --format='%(refname:short)%09%(objecttype)' \
    refs/tags)"
previous_tag="$(python3 - "$RELEASE_TAG" "$release_tags" <<'PY'
import re
import sys

release_tag, release_tags = sys.argv[1:]
pattern = re.compile(r"^v(\d{4})\.(\d{2})\.(\d{2})-([1-9]\d*)$")
current_match = pattern.fullmatch(release_tag)
if current_match is None:
    raise SystemExit(f"invalid release tag: {release_tag}")

current_version = tuple(map(int, current_match.groups()))
candidates = []
for line in release_tags.splitlines():
    tag, object_type = line.split("\t", 1)
    match = pattern.fullmatch(tag)
    if object_type != "tag" or match is None:
        continue
    version = tuple(map(int, match.groups()))
    if version < current_version:
        candidates.append((version, tag))

if candidates:
    print(max(candidates)[1])
PY
)"

cat <<'EOF'
## Changes

EOF

if [ -n "$previous_tag" ]; then
    if [ -n "${OOMOL_RELEASE_SUMMARY_API_KEY:-}" ]; then
        summary_file="$(mktemp)"
        summary_script="$(dirname "$0")/generate-release-summary.py"
        if python3 "$summary_script" \
            --repo-root "$repo_root" \
            --from-ref "$previous_tag" \
            --to-ref "$RELEASE_COMMIT_SHA" > "$summary_file"; then
            if [ -n "$release_summary_file" ]; then
                cat "$summary_file" > "$release_summary_file"
            fi
            printf '## Release summary\n\n'
            cat "$summary_file"
            printf '\n\n'
        else
            printf '%s\n' \
                'generate-release-notes: AI release summary failed; continuing with commit list' >&2
        fi
        rm -f "$summary_file"
    fi

    changes="$(git -C "$repo_root" log --first-parent \
        --format="- %s (\`%h\`)" "${previous_tag}..${RELEASE_COMMIT_SHA}")"
    if [ -n "$changes" ]; then
        printf '%s\n' "$changes"
    else
        printf -- "- No source changes since \`%s\`.\n" "$previous_tag"
    fi
else
    printf '%s\n' '- Initial public release.'
fi

cat <<EOF

## Build information

- Image: \`${RELEASE_IMAGE}\`
- Digest: \`${RELEASE_IMAGE_DIGEST}\`
- Source commit: \`${RELEASE_COMMIT_SHA}\`
- Hermes version: \`${RELEASE_HERMES_VERSION}\`
- OO CLI version: \`${RELEASE_OO_CLI_VERSION}\`
- Floating alias: \`${IMAGE_REPOSITORY}:latest\`

The immutable version tag, source-commit tag, and floating alias refer to the
same multi-platform registry digest at publication time.
EOF
