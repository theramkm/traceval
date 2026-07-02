#!/bin/bash
# traceval e2e quickstart: the whole loop now lives in `traceval demo`
# (generate traces -> ingest -> analyze -> generate evals -> run healthy
# agent, must pass -> run buggy agent, must fail).
set -e

uv run traceval demo -o traceval-demo --force "$@"
