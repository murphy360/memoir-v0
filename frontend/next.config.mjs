/** @type {import('next').NextConfig} */
const nextConfig = {
  // The app is served under a path prefix behind a reverse proxy (dontpanic.ddns.net/memoir).
  // Empty for local development, where it is the origin's root.
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",
  // Lint runs in CI (node-lint from murphy360/standards) with ESLint 9, which `next lint` on
  // Next 14 does not know how to drive.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
