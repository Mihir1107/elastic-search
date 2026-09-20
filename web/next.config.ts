import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Everything the browser calls goes through /api/proxy/* so the FastAPI host
  // (and any future auth header) is never exposed to the client bundle.
  env: {
    NEXT_PUBLIC_USE_MOCK: process.env.NEXT_PUBLIC_USE_MOCK ?? "true",
  },
};

export default config;
