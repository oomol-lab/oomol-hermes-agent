# Third-Party Notices

## Hermes Agent

This project builds on Hermes Agent:

- Source: <https://github.com/NousResearch/hermes-agent>
- Pinned revision: see `upstream.lock.json`
- License: MIT
- Copyright: Nous Research and Hermes Agent contributors

The Hermes source is downloaded during the image build and receives the small,
reviewable patch stored under `patches/`.

## OO CLI

The Docker image downloads a pinned OO CLI binary from OOMOL and verifies its
SHA-256 digest. Before the first public release, document the OO CLI's public
license and distribution terms here. The repository's MIT license does not
automatically relicense that binary.

## System And Python Dependencies

The image installs Debian packages and pinned Python packages listed in the
Dockerfile and `config/*-python-requirements.txt`. Those components retain their
respective licenses. Release automation should generate an SBOM and attach it
to published images.
