# Stage 1: Compilar
FROM gcc:12-bookworm AS builder

RUN apt-get update && apt-get install -y \
    libmodbus-dev libpq-dev make

WORKDIR /build
COPY src/ src/
COPY Makefile .

RUN make clean && make

# Stage 2: Runtime mínimo
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    libmodbus5 libpq5 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/modbus-reader /usr/local/bin/modbus-reader

ENTRYPOINT ["modbus-reader"]