import type { NextConfig } from "next";
import { API_URL } from './lib/config';

const isDev = process.env.NODE_ENV === 'development';

// Derive backend hostname/port from the env var so prod picks up the real domain without any changes here.
const apiUrl = new URL(API_URL);
const apiProtocol = apiUrl.protocol.replace(':', '') as 'http' | 'https';
const apiHostname = apiUrl.hostname;
const apiPort = apiUrl.port; // empty string when default (80/443)

// NEXT_PUBLIC_IMAGE_HOSTS — хости через кому, задаються на етапі збірки. Широких шаблонів
// (*.amazonaws.com, *.cloudfront.net) і хостів аукціонів за замовчуванням немає.
const imageHosts = (process.env.NEXT_PUBLIC_IMAGE_HOSTS ?? '')
  .split(',')
  .map((h) => h.trim().toLowerCase())
  .filter((h) => /^[a-z0-9.-]+$/.test(h) && !h.startsWith('*'));

const nextConfig: NextConfig = {
  async headers() {
    // Токен скидання пароля не має потрапляти в Referer при переході зі сторінки (задача 1.7).
    return [
      {
        source: '/password-reset/:path*',
        headers: [{ key: 'Referrer-Policy', value: 'no-referrer' }],
      },
    ];
  },
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
      // Хости сховища фото (R2/S3 custom domain), тільки https і конкретні хости (задача 7.2, 08-C8, 08-S10)
      ...imageHosts.map((hostname) => ({ protocol: 'https' as const, hostname })),
    ],
  },
};

export default nextConfig;
