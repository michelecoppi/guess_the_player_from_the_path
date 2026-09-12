/** Reviewed CSS literals only. Unknown styles require an explicit visual mapping.
 * The legacy grain SVG maps to a local CSS texture; no URLs are ever emitted. */
export const FRAME_PAINTS: ReadonlyMap<string, string> = new Map([
  [
    "repeating-linear-gradient(45deg, #f5c542 0 7px, #1b3a6b 7px 14px)",
    "repeating-linear-gradient(45deg, #f5c542 0 7px, #1b3a6b 7px 14px)"
  ],
  [
    "conic-gradient(#b8892f, #f7e39c, #d9b45b, #fff3c4, #b8892f)",
    "conic-gradient(#b8892f, #f7e39c, #d9b45b, #fff3c4, #b8892f)"
  ],
  [
    "conic-gradient(#ff4d4d, #ffb84d, #f5f24d, #4dff88, #4dc4ff, #8b4dff, #ff4d4d)",
    "conic-gradient(#ff4d4d, #ffb84d, #f5f24d, #4dff88, #4dc4ff, #8b4dff, #ff4d4d)"
  ],
  [
    "conic-gradient(#ffd000, #ff8a00, #ff2d00, #ff8a00, #ffd000)",
    "conic-gradient(#ffd000, #ff8a00, #ff2d00, #ff8a00, #ffd000)"
  ],
  [
    "repeating-conic-gradient(#233e66 0deg 55deg, #bddcff 65deg, #ffffff 72deg, #233e66 90deg)",
    "repeating-conic-gradient(#233e66 0deg 55deg, #bddcff 65deg, #ffffff 72deg, #233e66 90deg)"
  ],
  [
    "repeating-conic-gradient(#f4e5bb 0deg 12deg, #376b4b 12deg 18deg)",
    "repeating-conic-gradient(#f4e5bb 0deg 12deg, #376b4b 12deg 18deg)"
  ],
  [
    "repeating-linear-gradient(45deg, #c3ed68 0 2px, transparent 2px 8px), repeating-linear-gradient(-45deg, #c3ed68 0 2px, #263425 2px 8px)",
    "repeating-linear-gradient(45deg, #c3ed68 0 2px, transparent 2px 8px), repeating-linear-gradient(-45deg, #c3ed68 0 2px, #263425 2px 8px)"
  ],
  [
    "repeating-conic-gradient(#c98652 0deg 35deg, #f5e5c7 35deg 45deg)",
    "repeating-conic-gradient(#c98652 0deg 35deg, #f5e5c7 35deg 45deg)"
  ],
  [
    "repeating-conic-gradient(#f5c542 0deg 4deg, #1d3b2a 4deg 12deg)",
    "repeating-conic-gradient(#f5c542 0deg 4deg, #1d3b2a 4deg 12deg)"
  ],
  [
    "repeating-linear-gradient(0deg, #ede9e2 0 5px, #171614 5px 11px)",
    "repeating-linear-gradient(0deg, #ede9e2 0 5px, #171614 5px 11px)"
  ],
  [
    "repeating-linear-gradient(45deg, #ffd028 0 7px, #131007 7px 14px)",
    "repeating-linear-gradient(45deg, #ffd028 0 7px, #131007 7px 14px)"
  ],
  [
    "conic-gradient(#bfe6ff, #ffffff, #6ba8d8, #eaf6ff, #bfe6ff)",
    "conic-gradient(#bfe6ff, #ffffff, #6ba8d8, #eaf6ff, #bfe6ff)"
  ],
  [
    "repeating-conic-gradient(#6b5a3a 0deg 17deg, #3c452c 17deg 30deg)",
    "repeating-conic-gradient(#6b5a3a 0deg 17deg, #3c452c 17deg 30deg)"
  ],
  [
    "repeating-conic-gradient(#f2c74c 0deg 22deg, #123a72 22deg 45deg)",
    "repeating-conic-gradient(#f2c74c 0deg 22deg, #123a72 22deg 45deg)"
  ],
  [
    "repeating-conic-gradient(#4f7a45 0deg 9deg, #a8c98f 9deg 14deg, #4f7a45 14deg 20deg)",
    "repeating-conic-gradient(#4f7a45 0deg 9deg, #a8c98f 9deg 14deg, #4f7a45 14deg 20deg)"
  ],
  [
    "linear-gradient(135deg,#9fffd0,#42cbb8)",
    "linear-gradient(135deg,#9fffd0,#42cbb8)"
  ],
  [
    "linear-gradient(135deg,#c8f48b,#9fffd0)",
    "linear-gradient(135deg,#c8f48b,#9fffd0)"
  ]
]);
export const THEME_PATTERNS: ReadonlyMap<string, string> = new Map([
  [
    "linear-gradient(115deg, transparent 20%, rgba(188,220,255,.08) 21%, transparent 38%), linear-gradient(245deg, transparent 20%, rgba(188,220,255,.08) 21%, transparent 38%)",
    "linear-gradient(115deg, transparent 20%, rgba(188,220,255,.08) 21%, transparent 38%), linear-gradient(245deg, transparent 20%, rgba(188,220,255,.08) 21%, transparent 38%)"
  ],
  [
    "repeating-linear-gradient(0deg, transparent 0 5px, rgba(60,78,46,.035) 5px 6px)",
    "repeating-linear-gradient(0deg, transparent 0 5px, rgba(60,78,46,.035) 5px 6px)"
  ],
  [
    "repeating-linear-gradient(45deg, transparent 0 23px, rgba(195,237,104,.045) 23px 24px), repeating-linear-gradient(-45deg, transparent 0 23px, rgba(195,237,104,.045) 23px 24px)",
    "repeating-linear-gradient(45deg, transparent 0 23px, rgba(195,237,104,.045) 23px 24px), repeating-linear-gradient(-45deg, transparent 0 23px, rgba(195,237,104,.045) 23px 24px)"
  ],
  [
    "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)' opacity='.09'/%3E%3C/svg%3E\")",
    "repeating-linear-gradient(0deg, transparent 0 3px, #ded5c40a 3px 4px)"
  ],
  [
    "repeating-linear-gradient(0deg, rgba(255,208,40,.05) 0 1px, transparent 1px 7px)",
    "repeating-linear-gradient(0deg, rgba(255,208,40,.05) 0 1px, transparent 1px 7px)"
  ],
  [
    "repeating-radial-gradient(circle at 22% 10%, rgba(255,255,255,.14) 0 1.6px, transparent 2px 52px), repeating-radial-gradient(circle at 70% 40%, rgba(255,255,255,.1) 0 1.3px, transparent 2px 39px)",
    "repeating-radial-gradient(circle at 22% 10%, rgba(255,255,255,.14) 0 1.6px, transparent 2px 52px), repeating-radial-gradient(circle at 70% 40%, rgba(255,255,255,.1) 0 1.3px, transparent 2px 39px)"
  ],
  [
    "repeating-linear-gradient(100deg, rgba(107,90,58,.14) 0 3px, transparent 3px 16px)",
    "repeating-linear-gradient(100deg, rgba(107,90,58,.14) 0 3px, transparent 3px 16px)"
  ],
  [
    "radial-gradient(ellipse 90% 40% at 50% 108%, rgba(242,199,76,.22), transparent 70%)",
    "radial-gradient(ellipse 90% 40% at 50% 108%, rgba(242,199,76,.22), transparent 70%)"
  ],
  [
    "repeating-conic-gradient(from 0deg at 50% 0%, rgba(240,199,78,.05) 0deg 6deg, transparent 6deg 18deg)",
    "repeating-conic-gradient(from 0deg at 50% 0%, rgba(240,199,78,.05) 0deg 6deg, transparent 6deg 18deg)"
  ],
  [
    "linear-gradient(90deg,rgba(159,255,208,.025) 1px,transparent 1px),linear-gradient(rgba(159,255,208,.025) 1px,transparent 1px)",
    "linear-gradient(90deg,rgba(159,255,208,.025) 1px,transparent 1px),linear-gradient(rgba(159,255,208,.025) 1px,transparent 1px)"
  ]
]);

// A parsed texture can be safely parsed again.
