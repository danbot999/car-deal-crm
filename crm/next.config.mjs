import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  typedRoutes: false,
  turbopack: {
    root: fileURLToPath(new URL(".", import.meta.url))
  }
};

export default nextConfig;
