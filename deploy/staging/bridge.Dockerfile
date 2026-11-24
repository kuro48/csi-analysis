FROM node:22-bookworm-slim
WORKDIR /opt/csi/fabric
COPY fabric/package.json fabric/package-lock.json ./
RUN npm ci --omit=dev
COPY fabric/gateway.mjs fabric/gateway-server.mjs ./
COPY fabric/chaincode/lib/proof.js ./chaincode/lib/proof.js
CMD ["node", "gateway-server.mjs"]
