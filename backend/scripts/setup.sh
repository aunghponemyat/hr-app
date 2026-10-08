#!/usr/bin/env bash

# Install the backend from any working directory; do not source this script.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
poetry install --extras dev
