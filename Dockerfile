# =============================================================================
# Stage 1: Base environment
# Ubuntu 24.04 + Miniforge + conda-forge scientific stack
# See docs/adr/0001-arm64-base-image.md, docs/adr/0004-distributed-computing-support.md
# =============================================================================
FROM ubuntu:24.04 AS base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran cmake m4 wget curl git subversion \
    liblapack-dev libblas-dev graphviz xmlstarlet \
    ca-certificates locales sudo \
    perl libxml-libxml-perl \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    SHELL=/bin/bash

# Install Miniforge (architecture-aware: works for both amd64 and arm64)
ARG CONDA_DIR=/opt/conda
RUN wget -qO /tmp/miniforge.sh \
        "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-$(uname -m).sh" \
    && bash /tmp/miniforge.sh -b -p ${CONDA_DIR} \
    && rm /tmp/miniforge.sh \
    && ${CONDA_DIR}/bin/conda clean -afy

ENV PATH="${CONDA_DIR}/bin:${PATH}" \
    CONDA_PREFIX="${CONDA_DIR}"

# Install the scientific Python + compiled library stack from conda-forge.
# MPICH, HDF5, NetCDF, PNetCDF all come from conda-forge binaries (no source
# compilation needed). See docs/adr/0003-conda-environment-strategy.md and
# docs/adr/0004-distributed-computing-support.md.
#
# conda-lock.yml pins exact versions for both linux-64 and linux-aarch64.
# To update: edit environment.yml, then run:
#   conda-lock lock -f environment.yml -p linux-64 -p linux-aarch64 --mamba
# conda-lock.yml is the source of truth (pinned versions for both linux-64
# and linux-aarch64). We render the platform-appropriate explicit lockfile
# at build time and install from it. The pip dependencies declared in
# conda-lock.yml are installed separately since explicit lockfiles don't
# support them natively.
COPY conda-lock.yml /tmp/conda-lock.yml
COPY conda-linux-aarch64.lock conda-linux-64.lock /tmp/
RUN ARCH=$(uname -m) \
    && if [ "$ARCH" = "aarch64" ]; then LOCKFILE=/tmp/conda-linux-aarch64.lock; \
       else LOCKFILE=/tmp/conda-linux-64.lock; fi \
    && mamba install --name base --file "$LOCKFILE" --yes --quiet \
    && mamba clean -afy \
    && grep '^# pip ' "$LOCKFILE" \
       | sed 's/^# pip //' | sed 's/ @ / @ /' \
       | pip install --no-cache-dir --no-deps -r /dev/stdin \
    && rm /tmp/conda-lock.yml /tmp/conda-linux-*.lock

# Optional: Dask distributed stack (disabled by default).
# Build with --build-arg INSTALL_DASK_DISTRIBUTED=true to enable.
ARG INSTALL_DASK_DISTRIBUTED=false
COPY environment-dask.yml /tmp/environment-dask.yml
RUN if [ "$INSTALL_DASK_DISTRIBUTED" = "true" ]; then \
        mamba env update -n base -f /tmp/environment-dask.yml \
        && mamba clean -afy; \
    fi \
    && rm /tmp/environment-dask.yml

# pip-only dependencies that are already declared in environment.yml's pip
# section are installed above. requirements.txt is kept for any additional
# runtime-only packages (e.g., jupyterhub for DockerSpawner compatibility).
COPY requirements.txt /tmp/requirements.txt
RUN if [ -s /tmp/requirements.txt ] && grep -qvE '^\s*(#|$)' /tmp/requirements.txt; then \
        pip install --no-cache-dir -r /tmp/requirements.txt; \
    fi \
    && rm /tmp/requirements.txt

# Set PROJ_DATA so cartopy/GDAL find the PROJ database
ENV PROJ_DATA="${CONDA_DIR}/share/proj"


# =============================================================================
# Stage 2: CESM source + machine configuration
# =============================================================================
FROM base AS cesm

ARG CESM_TAG=release-cesm2.2.2
ARG CESM_ROOT=/opt/ncar/cesm

# Create user and group matching the upstream image convention
RUN groupadd -r cesm \
    && useradd -r -m -g cesm -G sudo -s /bin/bash user \
    && echo "user ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

RUN git clone --branch ${CESM_TAG} --depth 1 \
        https://github.com/ESCOMP/cesm.git ${CESM_ROOT} \
    && cd ${CESM_ROOT} \
    && ./manage_externals/checkout_externals \
    && for f in ${CESM_ROOT}/cime/src/externals/pio2/src/flib/pio_nf.F90 \
                ${CESM_ROOT}/cime/src/externals/pio2/src/flib/pio.F90; do \
         sed -i 's/PIO_HAS_PAR_FILTERS/DISABLED_PIO_HAS_PAR_FILTERS/g' "$f"; \
         sed -i 's/NC_HAS_MULTIFILTERS/DISABLED_NC_HAS_MULTIFILTERS/g' "$f"; \
         sed -i 's/NC_HAS_QUANTIZE/DISABLED_NC_HAS_QUANTIZE/g' "$f"; \
         sed -i 's/NC_HAS_ZSTD/DISABLED_NC_HAS_ZSTD/g' "$f"; \
         sed -i 's/NC_HAS_BZ/DISABLED_NC_HAS_BZ/g' "$f"; \
       done

# Install container machine configs (conda-forge paths, not /usr/local).
# See cesm-config/machines/ for the adapted XML files.
COPY cesm-config/machines/config_machines.xml \
     ${CESM_ROOT}/cime/config/cesm/machines/config_machines.xml
COPY cesm-config/machines/config_compilers.xml \
     ${CESM_ROOT}/cime/config/cesm/machines/config_compilers.xml
COPY cesm-config/machines/config_inputdata.xml \
     ${CESM_ROOT}/cime/config/cesm/config_inputdata.xml

# PE layout configs (all components use all available cores, single-threaded)
COPY cesm-config/cime_config/config_pes.xml \
     ${CESM_ROOT}/cime_config/config_pes.xml
COPY cesm-config/component_pes/cam/config_pes.xml \
     ${CESM_ROOT}/components/cam/cime_config/config_pes.xml
COPY cesm-config/component_pes/cice/config_pes.xml \
     ${CESM_ROOT}/components/cice/cime_config/config_pes.xml
COPY cesm-config/component_pes/cism/config_pes.xml \
     ${CESM_ROOT}/components/cism/cime_config/config_pes.xml
COPY cesm-config/component_pes/pop/config_pes.xml \
     ${CESM_ROOT}/components/pop/cime_config/config_pes.xml
COPY cesm-config/component_pes/clm/config_pes.xml \
     ${CESM_ROOT}/components/clm/cime_config/config_pes.xml

ENV CESMDATAROOT=/home/user \
    CIME_MACHINE=container \
    CESMROOT=${CESM_ROOT}

# Add CESM scripts to PATH
ENV PATH="${CESM_ROOT}/cime/scripts:${PATH}"

# Ensure all CESM files are owned by the user
RUN chown -R user:cesm ${CESM_ROOT}


# =============================================================================
# Stage 3: Project application layer
# This is the only stage that rebuilds on day-to-day code changes.
# =============================================================================
FROM cesm AS app

# Install reusable Python modules so they can be imported from any notebook
COPY --chown=user:cesm analytics_modules/ /opt/analytics_modules/
# CLM bundles an old six.py that shadows the real package and breaks dateutil.
# Remove it so the conda-forge six is found instead.
RUN find ${CESMROOT} -name "six.py" -not -path "*/site-packages/*" -delete \
 && find ${CESMROOT} -name "six_additions.py" -delete

ENV PYTHONPATH="/opt:/opt/analytics_modules:${CESMROOT}/components/clm/python:${CESMROOT}/cime/scripts/lib:${CESMROOT}/cime/scripts/Tools"

# Drop extended NEON wrapper next to the upstream run_neon.py
COPY --chown=user:cesm --chmod=0755 \
     cesm-tools/site_and_regional/run_neon_v2.py \
     ${CESMROOT}/tools/site_and_regional/run_neon_v2.py

# Expose NEON runners as PATH-resolvable commands
RUN ln -sf ${CESMROOT}/tools/site_and_regional/run_neon.py     /usr/local/bin/run_neon \
 && ln -sf ${CESMROOT}/tools/site_and_regional/run_neon_v2.py  /usr/local/bin/run_neon_v2

# Drop in notebooks and analysis code
COPY --chown=user:cesm notebooks/ /home/user/notebooks/

USER user
ENV USER=user
WORKDIR /home/user

EXPOSE 8888

CMD ["jupyter", "lab", "--ip=0.0.0.0", "--no-browser"]
