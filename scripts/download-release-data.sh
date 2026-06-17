#!/usr/bin/env bash
# Download CTSM input data from a GitHub Release and extract/reassemble.
# Called by the Dockerfile during the build. Not intended for direct use.
#
# Usage: download-release-data.sh <release-url> <inputdata-dir>

set -euo pipefail

RELEASE_URL="$1"
INPUTDATA="$2"

mkdir -p "$INPUTDATA"

# Compressed tarballs (atmosphere, land, small ndep)
for tarball in ctsm-inputdata-atm-v5.4.043.tar.zst \
               ctsm-inputdata-lnd-v5.4.043.tar.zst \
               ctsm-inputdata-ndep1-v5.4.043.tar.zst; do
    echo "Downloading $tarball..."
    wget -q --timeout=600 -O "/tmp/$tarball" "${RELEASE_URL}/$tarball"
    tar --zstd -xf "/tmp/$tarball" -C "$INPUTDATA"
    rm "/tmp/$tarball"
done

# Large nitrogen deposition file (split into raw parts, no compression)
NDEP_DIR="$INPUTDATA/lnd/clm2/ndepdata"
NDEP_FILE="fndep_clm_SSP370_b.e21.BWSSP370cmip6.f09_g17.CMIP6-SSP3-7.0-WACCM.002_1849-2101_monthly_0.9x1.25_c211216.nc"
mkdir -p "$NDEP_DIR"

echo "Downloading large ndep file (3 parts)..."
for part in aa ab ac; do
    wget -q --timeout=600 -O "/tmp/ndep2.$part" \
        "${RELEASE_URL}/ctsm-inputdata-ndep2-v5.4.043.$part"
done
cat /tmp/ndep2.aa /tmp/ndep2.ab /tmp/ndep2.ac > "$NDEP_DIR/$NDEP_FILE"
rm /tmp/ndep2.*

echo "Input data extracted to $INPUTDATA"
find "$INPUTDATA" -name "*.nc" -type f | wc -l | xargs -I{} echo "  {} NetCDF files"
