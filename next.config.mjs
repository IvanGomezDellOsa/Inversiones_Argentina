/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  rewrites: async () => {
    return [
      {
        source: "/api/:path*",
        destination: "/api/index",
      },
    ];
  },
}

export default nextConfig
