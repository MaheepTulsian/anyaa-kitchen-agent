#!/usr/bin/env sh
# Download the Claude Agent SDK wheel for the Docker image into vendor/ (resumable) and verify it.
# The wheel is 113 MB because it bundles the Claude CLI; uv can't resume broken downloads, curl can.
set -e
cd "$(dirname "$0")/.."
mkdir -p vendor
F=vendor/claude_agent_sdk-0.2.166-py3-none-manylinux_2_17_aarch64.whl
URL=https://files.pythonhosted.org/packages/2a/0d/b8fb131a4dcdf149b8384fac9258bcf6cf52df46d26ac1d321cd15f1d067/claude_agent_sdk-0.2.166-py3-none-manylinux_2_17_aarch64.whl
until curl -fL -C - --retry 10 --retry-all-errors -o "$F" "$URL"; do sleep 3; done
echo "3ba783eaaf0beba4cbc7278391ad4d5e4d7ec5cbc81355fcfea1fa865c0cebb7  $F" | shasum -a 256 -c
