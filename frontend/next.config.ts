import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === 'development';

// Derive backend hostname/port from the env var so prod picks up the real domain without any changes here.
const apiRaw = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const apiUrl = new URL(apiRaw);
const apiProtocol = apiUrl.protocol.replace(':', '') as 'http' | 'https';
const apiHostname = apiUrl.hostname;
const apiPort = apiUrl.port; // empty string when default (80/443)

const nextConfig: NextConfig = {
  images: {
    // In dev the Next.js image optimizer fetches from localhost, which resolves
    // to 127.0.0.1 — a private IP blocked by Next.js SSRF protection.
    // dangerouslyAllowLocalIP bypasses that check for dev only; prod is unaffected.
    dangerouslyAllowLocalIP: isDev,

    remotePatterns: [
      // Django backend media — host/port from NEXT_PUBLIC_API_URL
      {
        protocol: apiProtocol,
        hostname: apiHostname,
        ...(apiPort ? { port: apiPort } : {}),
        pathname: '/media/**',
      },
      // AWS S3 / Cloudflare R2 (prod)
      { protocol: 'https', hostname: '*.amazonaws.com' },
      { protocol: 'https', hostname: '*.r2.cloudflarestorage.com' },
      // Copart / IAAI CDN (source_url photos from lot import)
      { protocol: 'https', hostname: '*.copart.com' },
      { protocol: 'https', hostname: '*.iaai.com' },
      { protocol: 'https', hostname: '*.cloudfront.net' },
    ],
  },
};

export default nextConfig;
