FROM node:18-bullseye-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g ganache@7

EXPOSE 8545

CMD ["ganache", "--host", "0.0.0.0", "--port", "8545"]
