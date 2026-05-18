#!/usr/bin/env bash
# scripts/sandbox/build.sh — Build the pipelinekit sandbox base image locally.
#
# Image is intentionally local-only. No registry publication step is wired in;
# operators who want to share the image must configure their own infrastructure.
#
# Usage:
#   bash scripts/sandbox/build.sh [--engine podman|docker] [--tag <ref>] [--no-latest]
#
# Engine detection order: podman first, then docker. Override with --engine.
# Default tag: pipelinekit/sandbox-base:<git-short-sha>. Override with --tag.
# By default the build also applies the :latest alias locally; suppress with
# --no-latest.
#
# On success, prints the PIPELINEKIT_SANDBOX_TAG export line the sandbox
# providers consume.

set -euo pipefail

ENGINE=""
TAG_OVERRIDE=""
NO_LATEST=0

usage() {
  cat <<'EOF'
Usage: build.sh [--engine podman|docker] [--tag <ref>] [--no-latest] [-h|--help]

  --engine <name>   Force container engine (podman | docker). Default: auto-detect.
  --tag <ref>       Use this image ref instead of pipelinekit/sandbox-base:<sha>.
  --no-latest       Do not apply the pipelinekit/sandbox-base:latest alias.
  -h, --help        Show this help.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --engine)
      ENGINE="${2:-}"
      shift 2
      ;;
    --tag)
      TAG_OVERRIDE="${2:-}"
      shift 2
      ;;
    --no-latest)
      NO_LATEST=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "build.sh: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# Engine detection: explicit override first, else podman, else docker.
if [ -n "$ENGINE" ]; then
  case "$ENGINE" in
    podman|docker) ;;
    *)
      echo "build.sh: --engine must be podman or docker (got: $ENGINE)" >&2
      exit 2
      ;;
  esac
  if ! command -v "$ENGINE" >/dev/null 2>&1; then
    echo "build.sh: requested engine '$ENGINE' not found on PATH" >&2
    exit 1
  fi
elif command -v podman >/dev/null 2>&1; then
  ENGINE=podman
elif command -v docker >/dev/null 2>&1; then
  ENGINE=docker
else
  echo "build.sh: neither podman nor docker found on PATH; install one and retry" >&2
  exit 1
fi

# Compute the image tag.
if [ -n "$TAG_OVERRIDE" ]; then
  TAG="$TAG_OVERRIDE"
else
  if ! SHA=$(git rev-parse --short HEAD 2>/dev/null); then
    echo "build.sh: git rev-parse failed; not inside a git working tree?" >&2
    exit 1
  fi
  TAG="pipelinekit/sandbox-base:$SHA"
fi

LATEST_REF="pipelinekit/sandbox-base:latest"

# Idempotent: skip the build if the target tag already exists locally.
if "$ENGINE" image inspect "$TAG" >/dev/null 2>&1; then
  echo "build.sh: image $TAG already present locally (engine=$ENGINE); skipping build."
else
  echo "build.sh: building $TAG with engine=$ENGINE"
  "$ENGINE" build \
    -f scripts/sandbox/Containerfile \
    -t "$TAG" \
    scripts/sandbox/
fi

# Apply :latest alias unless suppressed. Re-tagging is idempotent.
if [ "$NO_LATEST" -eq 0 ] && [ "$TAG" != "$LATEST_REF" ]; then
  "$ENGINE" tag "$TAG" "$LATEST_REF"
  echo "build.sh: applied alias $LATEST_REF -> $TAG"
fi

cat <<EOF

Sandbox image ready: $TAG
To activate this tag in the providers, export:

  export PIPELINEKIT_SANDBOX_TAG=$TAG

(The providers also accept SANDBOX_PODMAN_IMAGE / SANDBOX_DOCKER_IMAGE for
per-engine overrides at higher precedence.)
EOF
