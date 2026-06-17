#!/usr/bin/env bash
#
# Create zstd-compressed tarballs of CTSM global input data and
# optionally upload them as a GitHub Release.
#
# Prerequisites:
#   - zstd (brew install zstd / apt install zstd)
#   - gh CLI (for --upload flag)
#
# Usage:
#   # Step 1: Download data (run once, takes 10-15 min)
#   docker run --rm \
#     -v "$(pwd)/scripts:/home/user/scripts:ro" \
#     -v /tmp/ctsm-inputdata:/home/user/inputdata \
#     exsoil-ctsm543-test bash -c \
#       'bash /home/user/scripts/pre-download-inputdata.sh /home/user/inputdata'
#
#   # Step 2: Create tarballs (and optionally upload)
#   ./scripts/create-inputdata-release.sh /tmp/ctsm-inputdata
#   ./scripts/create-inputdata-release.sh /tmp/ctsm-inputdata --upload

set -euo pipefail

CTSM_VERSION="v5.4.043"
RELEASE_TAG="inputdata-${CTSM_VERSION}"
REPO="UW-Madison-DSI/exsoil-nsf-prototype-refactor"

INPUTDATA="${1:?Usage: $0 <inputdata-dir> [--upload]}"
UPLOAD="${2:-}"

if [ ! -d "$INPUTDATA/lnd" ] || [ ! -d "$INPUTDATA/atm" ]; then
    echo "ERROR: $INPUTDATA does not look like a CTSM inputdata directory."
    echo "Expected subdirectories: atm/, lnd/, share/, cdeps/"
    exit 1
fi

OUTDIR="$(mktemp -d)"
echo "=== Creating tarballs in $OUTDIR ==="
echo ""

# Count files
FILE_COUNT=$(find "$INPUTDATA" -name "*.nc" -type f | wc -l | tr -d ' ')
echo "Found $FILE_COUNT NetCDF files in $INPUTDATA"
echo ""

# Tarball 1: atmosphere + coupler + shared meshes
echo "--- Tarball 1: atm + cdeps + share ---"
cd "$INPUTDATA"
tar --zstd -cf "$OUTDIR/ctsm-inputdata-atm-${CTSM_VERSION}.tar.zst" \
    atm/ cdeps/ share/ 2>/dev/null
echo "  $(ls -lh "$OUTDIR/ctsm-inputdata-atm-${CTSM_VERSION}.tar.zst" | awk '{print $5}')"

# Tarball 2: land model data (excluding large ndepdata)
echo "--- Tarball 2: lnd (excluding ndepdata) ---"
tar --zstd -cf "$OUTDIR/ctsm-inputdata-lnd-${CTSM_VERSION}.tar.zst" \
    --exclude='lnd/clm2/ndepdata' lnd/ 2>/dev/null
echo "  $(ls -lh "$OUTDIR/ctsm-inputdata-lnd-${CTSM_VERSION}.tar.zst" | awk '{print $5}')"

# Tarball 3: small ndep file
echo "--- Tarball 3: ndep (small file) ---"
tar --zstd -cf "$OUTDIR/ctsm-inputdata-ndep1-${CTSM_VERSION}.tar.zst" \
    lnd/clm2/ndepdata/fndep_clm_f09_g17.CMIP6-SSP3-7.0-WACCM_2018-2030_monthly_c210826.nc 2>/dev/null
echo "  $(ls -lh "$OUTDIR/ctsm-inputdata-ndep1-${CTSM_VERSION}.tar.zst" | awk '{print $5}')"

# Tarball 4: large ndep file (split into <2 GB parts)
echo "--- Tarball 4: ndep (large file, split into parts) ---"
tar --zstd -cf - \
    lnd/clm2/ndepdata/fndep_clm_SSP370_b.e21.BWSSP370cmip6.f09_g17.CMIP6-SSP3-7.0-WACCM.002_1849-2101_monthly_0.9x1.25_c211216.nc \
    | split -b 1900m - "$OUTDIR/ctsm-inputdata-ndep2-${CTSM_VERSION}.tar.zst."
ls -lh "$OUTDIR"/ctsm-inputdata-ndep2-*

# Checksums
echo ""
echo "--- Checksums ---"
cd "$OUTDIR"
shasum -a 256 ctsm-inputdata-* | tee checksums.sha256

echo ""
echo "=== Tarballs ready in $OUTDIR ==="
ls -lh "$OUTDIR"/ctsm-inputdata-*.tar.zst "$OUTDIR"/checksums.sha256

if [ "$UPLOAD" = "--upload" ]; then
    echo ""
    echo "=== Uploading to GitHub Release: $RELEASE_TAG ==="
    gh release create "$RELEASE_TAG" \
        --repo "$REPO" \
        --title "CTSM Input Data ${CTSM_VERSION}" \
        --notes "Static global input data for CTSM ${CTSM_VERSION} (tag ctsm5.4.043).

$FILE_COUNT NetCDF files, organized into two zstd-compressed tarballs.
Extract with: tar --zstd -xf <tarball> -C /path/to/inputdata

These files are static per CTSM version and do not need to be updated
unless the CTSM tag changes. NEON tower forcing data (site-specific,
~150 KB/month) is NOT included; it downloads at runtime from
storage.neonscience.org.

Checksums in checksums.sha256." \
        "$OUTDIR"/ctsm-inputdata-*.tar.zst \
        "$OUTDIR"/checksums.sha256

    echo ""
    echo "Release URL: https://github.com/$REPO/releases/tag/$RELEASE_TAG"
else
    echo ""
    echo "To upload, run:"
    echo "  $0 $INPUTDATA --upload"
fi
