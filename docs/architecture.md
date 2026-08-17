# Architecture

## Purpose

OOMOL Hermes Agent is a Docker distribution assembly project, not a fork that
develops an independent agent core.

```text
Pinned Hermes source
        |
        +-- minimal generic patch
        |
        +-- curated Hermes and OOMOL Skills
        |
        +-- OO framework Skills exported by OO CLI
        |
        +-- OOMOL provider Plugins
        |
        `-- immutable runtime image
                    |
                    `-- /data persistent user state
```

## Build-Time Layers

1. Download the immutable Hermes commit in `upstream.lock.json`.
2. Apply `patches/0001-skill-description-opt-in.patch` with a fail-closed check.
3. Install Hermes dependencies from its own lock file.
4. Install and verify the architecture-specific OO CLI binary.
5. Copy provider Plugins into Hermes's bundled Plugin categories.
6. Assemble allowlisted upstream and project-owned Skills into one immutable
   curated directory.
7. Export OO framework Skills into a separate immutable directory and add the
   Hermes routing-description metadata.
8. Exercise the document runtime and statically validate Plugin and Node code.

## Runtime State

All mutable state is below `/data`:

| Path | Purpose |
| --- | --- |
| `/data/.hermes` | Hermes configuration, sessions, user Skills, and state |
| `/data/.config/oo` | OO CLI configuration and the login persisted from the runtime API key |
| `/data/workspace` | Default agent workspace |

Image-owned code, Plugins, and Skills remain below `/opt` and are read-only at
runtime. Hermes lives at `/opt/hermes`, distribution assets live at
`/opt/oomol-hermes-agent`, and its virtual environment reuses the base image's
Python 3.11 interpreter, which remains executable after the container switches
to the non-root `hermes` user.

The entrypoint requires `OO_API_KEY`, `OO_LLM_BASE_URL`, `OO_LLM_MODEL`, and
`OO_LLM_API_MODE`. It validates the API mode against a small allowlist and
checks that the declared base URL is an HTTPS `/v1` endpoint before starting
Hermes. It then gives `oo auth login` up to 30 seconds to persist an OO CLI
login below `/data`; failure emits a warning but never prevents Hermes from
starting. Authentication is staged and atomically replaced; a failed refresh
removes the previous saved account so terminal work cannot silently use a stale
identity. It does not download Skills or health-check the model endpoint.

`OO_API_KEY` remains the runtime credential source for the main language model
and the other OO-backed providers. Its persisted OO CLI login allows terminal
processes, where Hermes deliberately strips provider environment credentials,
to use the bundled OO Skills. `OO_LLM_BASE_URL` declares the fixed OOMOL
endpoint, `OO_LLM_MODEL` selects the model, and `OO_LLM_API_MODE` selects either
`codex_responses` or `chat_completions`. Recommended values are declared in
`.env.example`; the runtime has no hidden endpoint, model, or API-mode fallback.

## Skill Description Exception

Hermes's global default remains 60 characters. A Skill can explicitly request a
larger prompt-index description through `metadata.hermes`, capped at 2,000
characters by the patch. The build adds a 1,200-character limit to the four OO
framework Skills. This avoids increasing the prompt footprint of every Skill.

## Plugin Providers

Provider Plugins adapt Hermes's existing provider ABCs to OOMOL inference and
OO connector actions:

- `oomol`: the main language-model provider, using the runtime-selected model
  and OpenAI-compatible API mode.
- `oo_gpt_image_2`: text-to-image and image editing.
- `oo_nano_banana`: Nano Banana image generation variants.
- `oo_seedance`: text/image-to-video generation.
- `oo_jina`: web search through Jina Reader.

They deliberately do not register generic `oo_search`, `oo_schema`, or `oo_run`
model tools. General connected-service work is routed through OO Skills and the
Hermes terminal.

## Configuration

`config/config.seed.yaml` is copied only when `$HERMES_HOME/config.yaml` does
not exist. Before Hermes starts, the entrypoint materializes its three
non-secret OOMOL model placeholders from the validated runtime environment and
records the values it owns in adjacent non-secret state. Later environment
changes refresh only those managed values; a field stops being managed after a
user customizes it. The same narrow migration removes the obsolete OOMOL
variables from the terminal passthrough list; only `OO_CONFIG_DIR` is needed
because oo-cli uses its persisted login. The seed enables the other bundled
providers and exposes their existing Hermes toolsets. Users retain full control
after first start.

Future configuration migrations must merge only missing distribution-owned
keys and must never replace user model, platform, Skill, or provider choices.
