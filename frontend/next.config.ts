import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      // Django dev media
      { protocol: 'http', hostname: 'localhost', port: '8000', pathname: '/media/**' },
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
