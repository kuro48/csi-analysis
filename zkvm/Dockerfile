FROM rust:1.90-bookworm AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN curl -L https://risczero.com/install | bash \
    && /root/.risc0/bin/rzup install
ENV PATH="/root/.risc0/bin:/root/.cargo/bin:${PATH}"

WORKDIR /src
COPY . .
# RISC Zero の C++ kernels は並列 + LTO だと Docker Desktop のメモリを
# 大きく消費するため、再現性を保ったままピーク使用量を抑える。
ENV CARGO_BUILD_JOBS=1 \
    CARGO_PROFILE_RELEASE_LTO=false \
    CARGO_PROFILE_RELEASE_CODEGEN_UNITS=8
RUN cargo build --release -p csi-zkvm-host

FROM debian:bookworm-slim
COPY --from=builder /src/target/release/csi-zkvm-host /usr/local/bin/csi-zkvm-host
RUN mkdir -p /out
CMD ["sh", "-c", "cp /usr/local/bin/csi-zkvm-host /out/csi-zkvm-host && chmod 755 /out/csi-zkvm-host"]
