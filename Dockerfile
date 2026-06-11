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
# conda-lock.yml pins exact versions for both linux-64 and linux-aarch64.
# To update: edit environment.yml, then run:
#   conda-lock lock -f environment.yml -p linux-64 -p linux-aarch64 --mamba
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

# pip-only dependencies from requirements.txt (if any)
COPY requirements.txt /tmp/requirements.txt
RUN if [ -s /tmp/requirements.txt ] && grep -qvE '^\s*(#|$)' /tmp/requirements.txt; then \
        pip install --no-cache-dir -r /tmp/requirements.txt; \
    fi \
    && rm /tmp/requirements.txt

# Set PROJ_DATA so cartopy/GDAL find the PROJ database
ENV PROJ_DATA="${CONDA_DIR}/share/proj"


# =============================================================================
# Stage 2: CTSM source + machine configuration
# Standalone CTSM with NEON tower workflow (ADR-0005)
# =============================================================================
FROM base AS ctsm

ARG CTSM_TAG=ctsm5.4.043
ARG CTSM_ROOT=/opt/ncar/ctsm

# Create user and group
RUN groupadd -r ctsm \
    && useradd -r -m -g ctsm -G sudo -s /bin/bash user \
    && echo "user ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Clone CTSM and check out external components.
# CTSM 5.2 uses manage_externals; 5.4+ uses git-fleximod.
RUN git clone --branch ${CTSM_TAG} \
        https://github.com/ESCOMP/CTSM.git ${CTSM_ROOT} \
    && cd ${CTSM_ROOT} \
    && if [ -x ./bin/git-fleximod ]; then \
         ./bin/git-fleximod update \
         || (git submodule update --init --recursive && ./bin/git-fleximod update); \
       elif [ -x ./manage_externals/checkout_externals ]; then \
         ./manage_externals/checkout_externals; \
       else \
         echo "ERROR: No checkout tool found" && exit 1; \
       fi

# Overlay container machine configs with conda-forge paths.
# ccs_config ships a container definition pointing at /usr/local;
# we override with $CONDA_PREFIX paths and arm64-safe GPTL flags.
COPY ctsm-config/machines/container/config_machines.xml \
     ${CTSM_ROOT}/ccs_config/machines/container/config_machines.xml
COPY ctsm-config/machines/container/container.cmake \
     ${CTSM_ROOT}/ccs_config/machines/container/container.cmake

# NEON usermods set MPILIB=mpi-serial, but conda-forge's MPICH is always
# on the library path. A binary built with CIME's mpi-serial stubs
# conflicts with the real MPICH .so at runtime, causing
# "MPI routine before initializing MPICH" errors. Remove the override
# so cases use the machine default (mpich).
RUN sed -i '/MPILIB=mpi-serial/d' \
    ${CTSM_ROOT}/cime_config/usermods_dirs/clm/NEON/defaults/shell_commands

ENV CESMDATAROOT=/home/user \
    CIME_MACHINE=container \
    CESMROOT=${CTSM_ROOT}

# Add CIME scripts to PATH
ENV PATH="${CTSM_ROOT}/cime/scripts:${PATH}"

# Ensure all CTSM files are owned by the user
RUN chown -R user:ctsm ${CTSM_ROOT}


# =============================================================================
# Stage 3: Project application layer
# This is the only stage that rebuilds on day-to-day code changes.
# =============================================================================
FROM ctsm AS app

# Install reusable Python modules so they can be imported from any notebook
COPY --chown=user:ctsm analytics_modules/ /opt/analytics_modules/

# CTSM Python modules are at the repo root (python/ctsm/), not under components/
ENV PYTHONPATH="/opt:/opt/analytics_modules:${CESMROOT}/python:${CESMROOT}/cime/scripts/lib:${CESMROOT}/cime/scripts/Tools"

# Drop extended NEON wrapper into CTSM tools directory
COPY --chown=user:ctsm --chmod=0755 \
     cesm-tools/site_and_regional/run_neon_v2.py \
     ${CESMROOT}/tools/site_and_regional/run_neon_v2.py

# Expose runners as PATH-resolvable commands
RUN ln -sf ${CESMROOT}/tools/site_and_regional/run_tower  /usr/local/bin/run_tower \
 && ln -sf ${CESMROOT}/tools/site_and_regional/run_neon_v2.py  /usr/local/bin/run_neon_v2

# Drop in notebooks and analysis code
COPY --chown=user:ctsm notebooks/ /home/user/notebooks/

USER user
ENV USER=user
RUN git config --global user.email "user@container" \
 && git config --global user.name "Container User"
WORKDIR /home/user

EXPOSE 8888

CMD ["jupyter", "lab", "--ip=0.0.0.0", "--no-browser"]
