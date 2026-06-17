# ADR-0009: Pin to CTSM development tag (ctsm5.4.043)

**Status:** Accepted (temporary)
**Date:** 2026-06-05
**Deciders:** Steven Wangen

## Context

The most recent official CTSM release is ctsm5.4.002 (December 2025).
Between that release and the current development branch, NCAR migrated
their data infrastructure from old FTP/SVN servers to a new GDEX server
(`osdf-data.gdex.ucar.edu`). The ctsm5.4.002 release shipped before
the configuration files (`config_inputdata.xml`) were updated to point
at the new server, so it references data locations that no longer exist.

Attempting to run ctsm5.4.002 fails at `check_input_data` because the
data files it expects are not on the servers it's configured to look at.

## Decision

Pin to `ctsm5.4.043`, a development tag on CTSM's `main` branch. This
was the earliest tag we found that has working GDEX server configuration
and can successfully download all required input data.

```dockerfile
ARG CTSM_TAG=ctsm5.4.043
```

## Consequences

- The container uses current CTSM code with working data access.
- We are tracking a development tag, not a stable release. Development
  tags are immutable (the commit they point to won't change), but they
  may include code that hasn't been through NCAR's full release
  testing.
- Any new bugs introduced between 5.4.002 and 5.4.043 are present in
  our container.
- When NCAR publishes a stable 5.4.x release with working GDEX
  configuration, we should upgrade to it and retire this workaround.

## Alternatives considered

| Option | Why rejected |
|--------|-------------|
| **ctsm5.4.002 (official release)** | Data server config broken; cannot download input data |
| **ctsm5.2.005 (older release)** | Incompatible with Python 3.13 (xml.etree type error); requires cmake <4 and Python <3.12 pins |
| **CTSM main branch HEAD** | Moving target; not reproducible across builds |
| **ctsm5.4.043 (chosen)** | Earliest tag with working GDEX config; immutable; validated end-to-end |
