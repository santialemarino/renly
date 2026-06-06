import createNextIntlPlugin from 'next-intl/plugin';

// Content-Security-Policy value, served in report-only mode (SEC-10). Report-only collects
// violation reports without blocking anything, so it cannot break the app. A real, enforced
// CSP for Next.js requires a per-request script nonce injected via middleware so that
// 'unsafe-inline' can be dropped from script-src; Next's inline bootstrap/runtime scripts
// would otherwise be blocked. That nonce work — and flipping this to the enforcing
// Content-Security-Policy header — is deferred to a follow-up.
const contentSecurityPolicyReportOnly = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "img-src 'self' data: https:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self'",
  "connect-src 'self'",
].join('; ');

// HTTP security headers applied to every route (SEC-10).
const securityHeaders = [
  // Force HTTPS for two years, including subdomains. Browsers ignore this over plain HTTP
  // (e.g. local dev), so sending it everywhere is safe.
  { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains' },
  // Stop the browser from MIME-sniffing a response away from the declared content type.
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  // Disallow framing entirely (clickjacking protection). CSP frame-ancestors mirrors this
  // once CSP is enforced.
  { key: 'X-Frame-Options', value: 'DENY' },
  // Send the full URL same-origin, only the origin cross-origin, and nothing on downgrade.
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  // Turn off powerful browser features the app never uses, so injected or third-party code
  // can't request them. Clipboard (used by the copy button) keeps its default same-origin
  // allowance since it isn't listed here.
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
  { key: 'Content-Security-Policy-Report-Only', value: contentSecurityPolicyReportOnly },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Apply the security headers to all routes.
  async headers() {
    return [
      {
        source: '/:path*',
        headers: securityHeaders,
      },
    ];
  },
  webpack(config) {
    const fileLoaderRule = config.module.rules.find((rule) => rule.test?.test?.('.svg'));
    if (!fileLoaderRule) return config;

    config.module.rules.push(
      // Reapply the existing rule, but only for svg imports ending in ?url
      {
        ...fileLoaderRule,
        test: /\.svg$/i,
        resourceQuery: /url/, // *.svg?url
      },
      // Convert all other *.svg imports to React components
      {
        test: /\.svg$/i,
        issuer: fileLoaderRule.issuer,
        resourceQuery: { not: [...fileLoaderRule.resourceQuery.not, /url/] }, // exclude if *.svg?url
        use: ['@svgr/webpack'],
      },
    );

    // Modify the file loader rule to ignore *.svg, since we have it handled now.
    fileLoaderRule.exclude = /\.svg$/i;

    return config;
  },
  turbopack: {
    root: '../..', // Workspace root for monorepo (fixes Docker build)
    rules: {
      '*.svg': {
        as: '*.js',
        loaders: ['@svgr/webpack'],
      },
    },
  },
};

const withNextIntl = createNextIntlPlugin();

export default withNextIntl(nextConfig);
