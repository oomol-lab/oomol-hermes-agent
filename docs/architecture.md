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
| `/data/.config/oo` | OO authentication and configuration |
| `/data/workspace` | Default agent workspace |

Image-owned code, Plugins, and Skills remain below `/opt` and are read-only at
runtime.

The entrypoint only creates missing directories and seeds Hermes configuration
on first start. It does not authenticate OO, download Skills, or call a remote
service.

## Skill Description Exception

Hermes's global default remains 60 characters. A Skill can explicitly request a
larger prompt-index description through `metadata.hermes`, capped at 2,000
characters by the patch. The build adds a 1,200-character limit to the four OO
framework Skills. This avoids increasing the prompt footprint of every Skill.

## Plugin Providers

Provider Plugins adapt Hermes's existing provider ABCs to OO connector actions:

- `oo_gpt_image_2`: text-to-image and image editing.
- `oo_nano_banana`: Nano Banana image generation variants.
- `oo_seedance`: text/image-to-video generation.
- `oo_jina`: web search through Jina Reader.

They deliberately do not register generic `oo_search`, `oo_schema`, or `oo_run`
model tools. General connected-service work is routed through OO Skills and the
Hermes terminal.

## Configuration

`config/config.seed.yaml` is copied only when `$HERMES_HOME/config.yaml` does
not exist. It enables bundled providers and exposes their existing Hermes
toolsets. Users retain full control after first start.

Future configuration migrations must merge only missing distribution-owned
keys and must never replace user model, platform, Skill, or provider choices.
