import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits a self-contained server in .next/standalone so the Docker runtime
  // image doesn't need the full node_modules tree.
  output: "standalone",
  poweredByHeader: false,
};

export default nextConfig;
