#!/usr/bin/env bash
#
# Run the container validation test suite.
#
# Usage:
#   ./tests/run_container_tests.sh                    # all tiers
#   ./tests/run_container_tests.sh tier0              # smoke tests only
#   ./tests/run_container_tests.sh tier0 tier1        # smoke + case creation
#   ./tests/run_container_tests.sh --image my-image   # custom image name
#
# This script starts the container, runs pytest inside it, and prints results.
# The container is removed after the run.

set -euo pipefail

IMAGE="exsoil-arm64-test"
TIERS=()
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --image)
            IMAGE="$2"
            shift 2
            ;;
        tier0|tier1|tier2)
            TIERS+=("$1")
            shift
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

MARKER=""
if [[ ${#TIERS[@]} -gt 0 ]]; then
    MARKER=$(printf "%s or " "${TIERS[@]}")
    MARKER="${MARKER% or }"
fi

CONTAINER_NAME="cesm-test-$$"

echo "=== Container Validation Tests ==="
echo "Image:  $IMAGE"
echo "Tiers:  ${TIERS[*]:-all}"
echo ""

PYTEST_CMD="pip install -q pytest > /dev/null 2>&1; python -m pytest /workspace/tests/ -v --tb=short"
if [[ -n "$MARKER" ]]; then
    PYTEST_CMD="$PYTEST_CMD -m '$MARKER'"
fi
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    PYTEST_CMD="$PYTEST_CMD ${EXTRA_ARGS[*]}"
fi

docker run --rm \
    --name "$CONTAINER_NAME" \
    -v "$(pwd)/tests:/workspace/tests:ro" \
    "$IMAGE" \
    bash -c "$PYTEST_CMD"
