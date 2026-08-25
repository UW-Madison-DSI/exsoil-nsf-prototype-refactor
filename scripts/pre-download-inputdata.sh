#!/usr/bin/env bash
#
# Pre-download CTSM input data files that CIME's check_input_data
# fails to retrieve reliably from NCAR's GDEX CDN.
#
# Usage:
#   ./scripts/pre-download-inputdata.sh [INPUTDATA_DIR]
#
# Default INPUTDATA_DIR: /home/user/inputdata (container default)
#
# This script downloads ~6 GB of global input data plus site-specific
# files. It tries GDEX first (with retries for CDN flakiness), then
# falls back to SVN or FTP. Files that already exist and are non-empty
# are skipped.
#
# The global data is static per CTSM version (ctsm5.4.043). It only
# needs to be downloaded once and can be cached on a persistent volume.

set -uo pipefail

INPUTDATA="${1:-/home/user/inputdata}"
mkdir -p "$INPUTDATA"

GDEX="https://osdf-data.gdex.ucar.edu/ncar/gdex/d651077/cesmdata/inputdata"
SVN="https://svn-ccsm-inputdata.cgd.ucar.edu/trunk/inputdata"
FTP="https://ftp.cgd.ucar.edu/cesm/inputdata"

PASS=0
FAIL=0
SKIP=0

download() {
    local relpath="$1"
    shift
    local dest="$INPUTDATA/$relpath"
    local fname=$(basename "$relpath")

    if [ -s "$dest" ]; then
        SKIP=$((SKIP+1))
        return 0
    fi

    mkdir -p "$(dirname "$dest")"

    for url in "$@"; do
        for attempt in 1 2 3 4 5; do
            wget --no-check-certificate -q --timeout=300 --tries=1 \
                 -O "$dest" "$url" 2>/dev/null
            if [ $? -eq 0 ] && [ -s "$dest" ]; then
                local size=$(du -h "$dest" | cut -f1)
                echo "  OK  $fname ($size)"
                PASS=$((PASS+1))
                return 0
            fi
            rm -f "$dest"
            sleep 2
        done
    done

    echo "  FAIL $fname"
    FAIL=$((FAIL+1))
    return 1
}

echo "=== CTSM Input Data Pre-Download ==="
echo "Target: $INPUTDATA"
echo ""

echo "--- Global parameter and physics files ---"
download "lnd/clm2/paramdata/ctsm60_params.c260518.nc" \
    "$GDEX/lnd/clm2/paramdata/ctsm60_params.c260518.nc" \
    "$SVN/lnd/clm2/paramdata/ctsm60_params.c260518.nc"

download "lnd/clm2/snicardata/snicar_optics_5bnd_c013122.nc" \
    "$GDEX/lnd/clm2/snicardata/snicar_optics_5bnd_c013122.nc" \
    "$SVN/lnd/clm2/snicardata/snicar_optics_5bnd_c013122.nc"

download "atm/cam/chem/trop_mozart/emis/megan21_emis_factors_78pft_c20161108.nc" \
    "$FTP/atm/cam/chem/trop_mozart/emis/megan21_emis_factors_78pft_c20161108.nc" \
    "$SVN/atm/cam/chem/trop_mozart/emis/megan21_emis_factors_78pft_c20161108.nc"

echo ""
echo "--- Atmosphere forcing ---"
download "atm/datm7/CO2/fco2_datm_global_simyr_1750-2014_CMIP6_c180929.nc" \
    "$FTP/atm/datm7/CO2/fco2_datm_global_simyr_1750-2014_CMIP6_c180929.nc" \
    "$SVN/atm/datm7/CO2/fco2_datm_global_simyr_1750-2014_CMIP6_c180929.nc"

download "atm/datm7/topo_forcing/topodata_0.9x1.25_USGS_070110_stream_c151201.nc" \
    "$FTP/atm/datm7/topo_forcing/topodata_0.9x1.25_USGS_070110_stream_c151201.nc" \
    "$SVN/atm/datm7/topo_forcing/topodata_0.9x1.25_USGS_070110_stream_c151201.nc"

download "atm/datm7/topo_forcing/topodata_0.9x1.SCRIP.210520_ESMFmesh.nc" \
    "$SVN/atm/datm7/topo_forcing/topodata_0.9x1.SCRIP.210520_ESMFmesh.nc" \
    "$GDEX/atm/datm7/topo_forcing/topodata_0.9x1.SCRIP.210520_ESMFmesh.nc"

download "cdeps/datm/ozone/O3_surface.f09_g17.CMIP6-SSP3-7.0-WACCM.001.monthly.201501-210012.nc" \
    "$SVN/cdeps/datm/ozone/O3_surface.f09_g17.CMIP6-SSP3-7.0-WACCM.001.monthly.201501-210012.nc" \
    "$GDEX/cdeps/datm/ozone/O3_surface.f09_g17.CMIP6-SSP3-7.0-WACCM.001.monthly.201501-210012.nc"

download "atm/cam/chem/trop_mozart_aero/aero/aerodep_clm_SSP370_b.e21.BWSSP370cmip6.f09_g17.CMIP6-SSP3-7.0-WACCM.001_2018-2030_monthly_0.9x1.25_c210826.nc" \
    "$FTP/atm/cam/chem/trop_mozart_aero/aero/aerodep_clm_SSP370_b.e21.BWSSP370cmip6.f09_g17.CMIP6-SSP3-7.0-WACCM.001_2018-2030_monthly_0.9x1.25_c210826.nc" \
    "$SVN/atm/cam/chem/trop_mozart_aero/aero/aerodep_clm_SSP370_b.e21.BWSSP370cmip6.f09_g17.CMIP6-SSP3-7.0-WACCM.001_2018-2030_monthly_0.9x1.25_c210826.nc"

echo ""
echo "--- Nitrogen deposition (large files) ---"
download "lnd/clm2/ndepdata/fndep_clm_SSP370_b.e21.BWSSP370cmip6.f09_g17.CMIP6-SSP3-7.0-WACCM.002_1849-2101_monthly_0.9x1.25_c211216.nc" \
    "$SVN/lnd/clm2/ndepdata/fndep_clm_SSP370_b.e21.BWSSP370cmip6.f09_g17.CMIP6-SSP3-7.0-WACCM.002_1849-2101_monthly_0.9x1.25_c211216.nc" \
    "$GDEX/lnd/clm2/ndepdata/fndep_clm_SSP370_b.e21.BWSSP370cmip6.f09_g17.CMIP6-SSP3-7.0-WACCM.002_1849-2101_monthly_0.9x1.25_c211216.nc"

download "lnd/clm2/ndepdata/fndep_clm_f09_g17.CMIP6-SSP3-7.0-WACCM_2018-2030_monthly_c210826.nc" \
    "$FTP/lnd/clm2/ndepdata/fndep_clm_f09_g17.CMIP6-SSP3-7.0-WACCM_2018-2030_monthly_c210826.nc" \
    "$SVN/lnd/clm2/ndepdata/fndep_clm_f09_g17.CMIP6-SSP3-7.0-WACCM_2018-2030_monthly_c210826.nc"

echo ""
echo "--- Mesh files ---"
download "share/meshes/fv0.9x1.25_141008_polemod_ESMFmesh.nc" \
    "$FTP/share/meshes/fv0.9x1.25_141008_polemod_ESMFmesh.nc" \
    "$SVN/share/meshes/fv0.9x1.25_141008_polemod_ESMFmesh.nc"

download "lnd/clm2/dustemisdata/dust_0.25x0.25_ESMFmesh_cdf5_c240222.nc" \
    "$SVN/lnd/clm2/dustemisdata/dust_0.25x0.25_ESMFmesh_cdf5_c240222.nc" \
    "$GDEX/lnd/clm2/dustemisdata/dust_0.25x0.25_ESMFmesh_cdf5_c240222.nc"

download "lnd/clm2/paramdata/exice_init_0.125x0.125_ESMFmesh_cdf5_c20220802.nc" \
    "$SVN/lnd/clm2/paramdata/exice_init_0.125x0.125_ESMFmesh_cdf5_c20220802.nc" \
    "$GDEX/lnd/clm2/paramdata/exice_init_0.125x0.125_ESMFmesh_cdf5_c20220802.nc"

download "lnd/clm2/paramdata/finundated_inversiondata_0.9x1_ESMFmesh_cdf5_130621.nc" \
    "$SVN/lnd/clm2/paramdata/finundated_inversiondata_0.9x1_ESMFmesh_cdf5_130621.nc"

download "lnd/clm2/urbandata/CLM50_tbuildmax_Oleson_2016_0.9x1_ESMFmesh_cdf5_100621.nc" \
    "$FTP/lnd/clm2/urbandata/CLM50_tbuildmax_Oleson_2016_0.9x1_ESMFmesh_cdf5_100621.nc" \
    "$SVN/lnd/clm2/urbandata/CLM50_tbuildmax_Oleson_2016_0.9x1_ESMFmesh_cdf5_100621.nc"

echo ""
echo "--- Urban and crop data ---"
download "lnd/clm2/urbandata/CTSM52_urbantv_Li_2024_0.9x1.25_simyr1849-2106_c20260217.nc" \
    "$GDEX/lnd/clm2/urbandata/CTSM52_urbantv_Li_2024_0.9x1.25_simyr1849-2106_c20260217.nc"

download "lnd/clm2/cropdata/calendars/processed/swindow_starts_ggcmi_crop_calendar_phase3_v1.01.2000-2000.20231005_145103.tweaked_latlons.no_nan_fill.nc" \
    "$GDEX/lnd/clm2/cropdata/calendars/processed/swindow_starts_ggcmi_crop_calendar_phase3_v1.01.2000-2000.20231005_145103.tweaked_latlons.no_nan_fill.nc"

download "lnd/clm2/cropdata/calendars/processed/swindow_ends_ggcmi_crop_calendar_phase3_v1.01.2000-2000.20231005_145103.tweaked_latlons.no_nan_fill.nc" \
    "$GDEX/lnd/clm2/cropdata/calendars/processed/swindow_ends_ggcmi_crop_calendar_phase3_v1.01.2000-2000.20231005_145103.tweaked_latlons.no_nan_fill.nc"

download "lnd/clm2/cropdata/calendars/processed/20230714_cropcals_pr2_1deg.actually2deg.1980-2009.from_GDDB20.interpd_halfdeg.tweaked_latlons.no_nan_fill.nc" \
    "$GDEX/lnd/clm2/cropdata/calendars/processed/20230714_cropcals_pr2_1deg.actually2deg.1980-2009.from_GDDB20.interpd_halfdeg.tweaked_latlons.no_nan_fill.nc"

download "lnd/clm2/cropdata/calendars/processed/360x720_120830_ESMFmesh_c20210507_cdf5.tweaked_latlons.no_nan_fill.nc" \
    "$GDEX/lnd/clm2/cropdata/calendars/processed/360x720_120830_ESMFmesh_c20210507_cdf5.tweaked_latlons.no_nan_fill.nc"

echo ""
echo "--- NEON site surface data (KONZ) ---"
download "lnd/clm2/surfdata_esmf/NEON/ctsm5.4.0/surfdata_1x1_NEON_KONZ_hist_2000_78pfts_c251023.no_nan_fill.nc" \
    "$GDEX/lnd/clm2/surfdata_esmf/NEON/ctsm5.4.0/surfdata_1x1_NEON_KONZ_hist_2000_78pfts_c251023.no_nan_fill.nc"

echo ""
echo "--- Additional data (discovered in build/run stage) ---"
download "lnd/clm2/cropdata/calendars/processed/gdds_20230829_161011.tweaked_latlons.no_nan_fill.nc" \
    "$GDEX/lnd/clm2/cropdata/calendars/processed/gdds_20230829_161011.tweaked_latlons.no_nan_fill.nc"

download "lnd/clm2/paramdata/exice_init_0.125x0.125_c20220516.nc" \
    "$SVN/lnd/clm2/paramdata/exice_init_0.125x0.125_c20220516.nc" \
    "$GDEX/lnd/clm2/paramdata/exice_init_0.125x0.125_c20220516.nc"

download "lnd/clm2/dustemisdata/Prigent_2005_roughness_0.25x0.25_cdf5_c260218.nc" \
    "$GDEX/lnd/clm2/dustemisdata/Prigent_2005_roughness_0.25x0.25_cdf5_c260218.nc"

download "atm/datm7/NASA_LIS/clmforc.Li_2016_climo1995-2013.360x720.lnfm_Total_NEONarea_c210625.nc" \
    "$FTP/atm/datm7/NASA_LIS/clmforc.Li_2016_climo1995-2013.360x720.lnfm_Total_NEONarea_c210625.nc" \
    "$SVN/atm/datm7/NASA_LIS/clmforc.Li_2016_climo1995-2013.360x720.lnfm_Total_NEONarea_c210625.nc"

download "atm/datm7/NASA_LIS/ESMF_MESH.Li_2016.360x720.NEONarea_cdf5_c221104.nc" \
    "$FTP/atm/datm7/NASA_LIS/ESMF_MESH.Li_2016.360x720.NEONarea_cdf5_c221104.nc" \
    "$SVN/atm/datm7/NASA_LIS/ESMF_MESH.Li_2016.360x720.NEONarea_cdf5_c221104.nc"

download "lnd/clm2/snicardata/snicar_drdt_bst_fit_60_c070416.nc" \
    "$FTP/lnd/clm2/snicardata/snicar_drdt_bst_fit_60_c070416.nc" \
    "$SVN/lnd/clm2/snicardata/snicar_drdt_bst_fit_60_c070416.nc"

download "lnd/clm2/firedata/clmforc.Li_2017_HYDEv3.2_CMIP6_hdm_0.5x0_ESMFmesh_cdf5_100621.nc" \
    "$FTP/lnd/clm2/firedata/clmforc.Li_2017_HYDEv3.2_CMIP6_hdm_0.5x0_ESMFmesh_cdf5_100621.nc" \
    "$SVN/lnd/clm2/firedata/clmforc.Li_2017_HYDEv3.2_CMIP6_hdm_0.5x0_ESMFmesh_cdf5_100621.nc"

download "lnd/clm2/firedata/clmforc.Li_2025_CMIP7_SSP3CMIP6_hdm_0.5x0.5_simyr1850-2100_c250717.nc" \
    "$GDEX/lnd/clm2/firedata/clmforc.Li_2025_CMIP7_SSP3CMIP6_hdm_0.5x0.5_simyr1850-2100_c250717.nc"

download "lnd/clm2/paramdata/finundated_inversiondata_0.9x1.25_c170706.nc" \
    "$FTP/lnd/clm2/paramdata/finundated_inversiondata_0.9x1.25_c170706.nc" \
    "$SVN/lnd/clm2/paramdata/finundated_inversiondata_0.9x1.25_c170706.nc"

# NOTE: NEON tower forcing data (150 KB/month) is NOT pre-downloaded here.
# CIME downloads it directly into the case's run/inputdata/ directory
# from storage.neonscience.org during check_input_data. Those files are
# small, fast, and go to a different path than $DIN_LOC_ROOT.

echo ""
echo "========================================="
echo "  Downloaded: $PASS"
echo "  Skipped:    $SKIP"
echo "  Failed:     $FAIL"
echo "========================================="

if [ $FAIL -gt 0 ]; then
    echo "WARNING: $FAIL files failed to download. The simulation may not run."
    exit 1
fi
