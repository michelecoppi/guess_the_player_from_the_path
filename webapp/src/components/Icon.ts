/** One outline family. All icons are decorative; the control supplies its label. */
const paths = {
  career:
    '<path d="M5 3h14v18H5zM5 12h14M9 3v4h6V3M9 21v-4h6v4"/><circle cx="12" cy="12" r="3"/>',
  arena:
    '<path d="m4 3 8 8-3 3-7-8V3h2Zm16 0-8 8 3 3 7-8V3h-2ZM4 16l4 4m-6 2 7-7m11 1-4 4m6 2-7-7"/>',
  ranking:
    '<path d="M8 3h8v5a4 4 0 0 1-8 0V3Zm0 2H4v3a4 4 0 0 0 5 4m7-7h4v3a4 4 0 0 1-5 4m-3 0v6m-5 3h10m-8 0v-3h6v3"/>',
  archive:
    '<rect x="3" y="5" width="18" height="16" rx="1"/><path d="M7 3v4m10-4v4M3 10h18m-14 4h3m4 0h3m-10 4h3"/>',
  profile:
    '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  reports: '<path d="M4 3h16v13H9l-5 5V3Zm8 4v4m0 2v1"/>',
  refunds: '<path d="M7 4h13v16H7M4 7l-3 3 3 3m-3-3h10m0 6h5"/>',
  privacy:
    '<path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6l9-4Zm-3 8 6 6m0-6-6 6"/>',
  back: '<path d="M20 12H4m6-6-6 6 6 6"/>',
  more: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  hint: '<path d="M9 18h6m-5 3h4M8 14a6 6 0 1 1 8 0l-1 1H9l-1-1Z"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  warning: '<path d="m12 3 10 18H2L12 3Zm0 6v5m0 3v1"/>',
  shop: '<path d="M4 8h16l-1 13H5L4 8Zm4 0V6a4 4 0 0 1 8 0v2"/>',
  referral:
    '<circle cx="8" cy="7" r="3"/><path d="M2 20v-2a6 6 0 0 1 12 0v2m2-16a3 3 0 0 1 0 6m1 4a5 5 0 0 1 5 5"/>',
  events: '<path d="M5 21V3m0 1h14l-3 5 3 5H5"/>',
} as const;
export type IconName = keyof typeof paths;
export function icon(name: IconName): string {
  return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]}</svg>`;
}
