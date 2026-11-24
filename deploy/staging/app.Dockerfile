FROM rust:1.90-bookworm AS prover
WORKDIR /build
COPY zkp/native-prover/Cargo.toml zkp/native-prover/Cargo.lock ./
COPY zkp/native-prover/src ./src
RUN cargo build --locked --release

FROM node:22-bookworm-slim AS node
WORKDIR /zkp
COPY zkp/package.json zkp/package-lock.json ./
RUN npm ci --omit=dev

FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libpq5 curl git build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /zkp/node_modules /zkp/node_modules
COPY --from=prover /build/target/release/csi-native-prover /usr/local/bin/csi-native-prover
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY zkp/scripts/prove_adaptive_capture.cjs /zkp/scripts/prove_adaptive_capture.cjs
COPY deploy/staging/runtime.py /opt/csi/runtime.py
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 ZKP_AUTO_COMPILE=false
ENTRYPOINT ["python", "/opt/csi/runtime.py"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
