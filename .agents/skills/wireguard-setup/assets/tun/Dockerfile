# Module-only builder; no firmware flashing tools or device access.
FROM debian:bookworm-20260202-slim@sha256:98f4b71de414932439ac6ac690d7060df1f27161073c5036a7553723881bffbe
ARG SNAPSHOT=20260201T000000Z
RUN printf 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/%s bookworm main\n' "$SNAPSHOT" > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends build-essential gcc-arm-linux-gnueabihf python3 patch bison flex bc \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
ENTRYPOINT ["/bin/sh"]
