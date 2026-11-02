import http from "node:http";
import { readFileSync } from "node:fs";
import { timingSafeEqual } from "node:crypto";
import { openGateway } from "./gateway.mjs";

const config = JSON.parse(readFileSync(process.env.FABRIC_GATEWAY_CONFIG));
const role = process.env.FABRIC_BRIDGE_ROLE;
const token = process.env.FABRIC_BRIDGE_TOKEN;
if (!token || token.length < 32)
  throw new Error("Set a bridge token of at least 32 characters");
const gateway = openGateway(config, role);
await gateway.configuration();
const server = http.createServer(async (req, res) => {
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "no-store");
  const supplied = Buffer.from(req.headers.authorization || ""),
    expected = Buffer.from("Bearer " + token);
  if (
    supplied.length !== expected.length ||
    !timingSafeEqual(supplied, expected)
  ) {
    res.writeHead(401);
    res.end("{}");
    return;
  }
  try {
    let bytes = 0;
    const parts = [];
    for await (const chunk of req) {
      bytes += chunk.length;
      if (bytes > 20000) throw new Error("Body too large");
      parts.push(chunk);
    }
    const data = parts.length
      ? JSON.parse(Buffer.concat(parts).toString())
      : {};
    let result;
    if (req.method === "GET" && req.url === "/configuration")
      result = await gateway.configuration();
    else if (req.method === "POST" && req.url === "/metadata")
      result = await gateway.metadata(data.observationId);
    else if (
      req.method === "POST" &&
      req.url === "/verify" &&
      role === "reader"
    )
      result = (await gateway.verify(data.observationId)).result;
    else if (
      req.method === "POST" &&
      req.url === "/record" &&
      role === "writer"
    )
      result = await gateway.record(data);
    else {
      res.writeHead(404);
      res.end("{}");
      return;
    }
    res.end(JSON.stringify(result));
  } catch (error) {
    // Do not leak credentials, peer addresses, proof payloads, or gateway errors to callers.
    console.error("Fabric operation failed:", error.name);
    res.writeHead(503);
    res.end(
      JSON.stringify({
        error: "Fabric operation failed; no verified result available",
      }),
    );
  }
});
server.requestTimeout = 150000;
server.listen(
  Number(process.env.FABRIC_BRIDGE_PORT || (role === "reader" ? 8801 : 8802)),
  process.env.FABRIC_BRIDGE_HOST || "127.0.0.1",
);
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () =>
    server.close(() => {
      gateway.close();
      process.exit(0);
    }),
  );
