/** Reviewed CSS literals only. Unknown styles require an explicit visual mapping.
 * The legacy grain SVG maps to a local CSS texture; no URLs are ever emitted. */
export const FRAME_PAINTS: ReadonlyMap<string, string> = new Map([
  ["conic-gradient(from 200deg, #5ef0b0, #3fc4e8, #a678ff, #5ef0b0)", "conic-gradient(from 200deg, #5ef0b0, #3fc4e8, #a678ff, #5ef0b0)"],
  ["repeating-conic-gradient(#ff5a4d 0deg 15deg, #fff1ec 15deg 30deg)", "repeating-conic-gradient(#ff5a4d 0deg 15deg, #fff1ec 15deg 30deg)"],
  ["repeating-conic-gradient(#7cff4f 0deg 30deg, #10162a 30deg 45deg, #4f7cff 45deg 75deg, #10162a 75deg 90deg)", "repeating-conic-gradient(#7cff4f 0deg 30deg, #10162a 30deg 45deg, #4f7cff 45deg 75deg, #10162a 75deg 90deg)"],
  ["conic-gradient(#ffd6e7, #ff9ec7, #fff0f6, #ff7fb0, #ffd6e7)", "conic-gradient(#ffd6e7, #ff9ec7, #fff0f6, #ff7fb0, #ffd6e7)"],
  ["repeating-linear-gradient(0deg, #ffc46b 0 6px, #5ed6e0 6px 12px)", "repeating-linear-gradient(0deg, #ffc46b 0 6px, #5ed6e0 6px 12px)"],
  ["conic-gradient(from 90deg, #2d2860, #b69cff, #ffd98a, #6fd0ff, #2d2860)", "conic-gradient(from 90deg, #2d2860, #b69cff, #ffd98a, #6fd0ff, #2d2860)"],
  ["repeating-conic-gradient(#9fd3ff 0deg 8deg, #18222d 8deg 20deg, #fff38a 20deg 24deg, #18222d 24deg 36deg)", "repeating-conic-gradient(#9fd3ff 0deg 8deg, #18222d 8deg 20deg, #fff38a 20deg 24deg, #18222d 24deg 36deg)"],
  ["repeating-conic-gradient(#ff824e 0deg 24deg, #63213f 24deg 30deg)", "repeating-conic-gradient(#ff824e 0deg 24deg, #63213f 24deg 30deg)"],
  ["repeating-conic-gradient(#edbe7e 0deg 12deg, #302a26 12deg 16deg)", "repeating-conic-gradient(#edbe7e 0deg 12deg, #302a26 12deg 16deg)"],
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
  ["radial-gradient(ellipse 70% 38% at 18% 8%, rgba(94,240,176,.16), transparent 70%), radial-gradient(ellipse 60% 30% at 82% 18%, rgba(166,120,255,.14), transparent 70%), repeating-linear-gradient(100deg, transparent 0 34px, rgba(94,240,176,.03) 34px 36px)", "radial-gradient(ellipse 70% 38% at 18% 8%, rgba(94,240,176,.16), transparent 70%), radial-gradient(ellipse 60% 30% at 82% 18%, rgba(166,120,255,.14), transparent 70%), repeating-linear-gradient(100deg, transparent 0 34px, rgba(94,240,176,.03) 34px 36px)"],
  ["repeating-linear-gradient(90deg, rgba(255,90,77,.06) 0 11px, transparent 11px 22px), repeating-linear-gradient(0deg, rgba(255,255,255,.035) 0 11px, transparent 11px 22px)", "repeating-linear-gradient(90deg, rgba(255,90,77,.06) 0 11px, transparent 11px 22px), repeating-linear-gradient(0deg, rgba(255,255,255,.035) 0 11px, transparent 11px 22px)"],
  ["repeating-linear-gradient(0deg, rgba(124,255,79,.05) 0 2px, transparent 2px 6px), repeating-linear-gradient(90deg, rgba(90,120,255,.04) 0 1px, transparent 1px 12px)", "repeating-linear-gradient(0deg, rgba(124,255,79,.05) 0 2px, transparent 2px 6px), repeating-linear-gradient(90deg, rgba(90,120,255,.04) 0 1px, transparent 1px 12px)"],
  ["radial-gradient(ellipse 5px 3px at 8% 12%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 3px at 23% 64%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 6px 3px at 37% 28%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 2px at 49% 81%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 5px 3px at 58% 14%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 3px at 66% 52%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 6px 3px at 79% 33%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 5px 3px at 88% 71%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 2px at 15% 88%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 3px at 94% 11%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 3px 2px at 31% 45%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 2px at 72% 91%, rgba(255,158,199,.32), transparent)", "radial-gradient(ellipse 5px 3px at 8% 12%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 3px at 23% 64%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 6px 3px at 37% 28%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 2px at 49% 81%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 5px 3px at 58% 14%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 3px at 66% 52%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 6px 3px at 79% 33%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 5px 3px at 88% 71%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 2px at 15% 88%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 3px at 94% 11%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 3px 2px at 31% 45%, rgba(255,158,199,.32), transparent), radial-gradient(ellipse 4px 2px at 72% 91%, rgba(255,158,199,.32), transparent)"],
  ["repeating-radial-gradient(circle at 50% 120%, transparent 0 22px, rgba(94,214,224,.05) 22px 24px), linear-gradient(180deg, transparent 60%, rgba(255,196,107,.07))", "repeating-radial-gradient(circle at 50% 120%, transparent 0 22px, rgba(94,214,224,.05) 22px 24px), linear-gradient(180deg, transparent 60%, rgba(255,196,107,.07))"],
  ["radial-gradient(circle at 6% 14%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 19% 71%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 27% 33%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 38% 88%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 44% 12%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 53% 57%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 61% 26%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 69% 79%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 77% 43%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 86% 9%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 92% 64%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 12% 47%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 33% 60%, #ffffff5c 1.5px, transparent 2.1px)", "radial-gradient(circle at 6% 14%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 19% 71%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 27% 33%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 38% 88%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 44% 12%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 53% 57%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 61% 26%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 69% 79%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 77% 43%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 86% 9%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 92% 64%, #ffffff5c 1.5px, transparent 2.1px), radial-gradient(circle at 12% 47%, #b69cff4d 1.0px, transparent 1.6px), radial-gradient(circle at 33% 60%, #ffffff5c 1.5px, transparent 2.1px)"],
  ["repeating-linear-gradient(105deg, transparent 0 18px, rgba(159,211,255,.07) 18px 19px, transparent 19px 41px), radial-gradient(ellipse 80% 30% at 50% 0%, rgba(255,243,138,.06), transparent 70%)", "repeating-linear-gradient(105deg, transparent 0 18px, rgba(159,211,255,.07) 18px 19px, transparent 19px 41px), radial-gradient(ellipse 80% 30% at 50% 0%, rgba(255,243,138,.06), transparent 70%)"],
  ["repeating-linear-gradient(0deg, transparent 0 28px, rgba(255,173,97,.06) 28px 29px)", "repeating-linear-gradient(0deg, transparent 0 28px, rgba(255,173,97,.06) 28px 29px)"],
  ["repeating-linear-gradient(90deg, transparent 0 27px, rgba(237,190,126,.045) 27px 28px)", "repeating-linear-gradient(90deg, transparent 0 27px, rgba(237,190,126,.045) 27px 28px)"],
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
    "radial-gradient(circle at 6% 12%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 24% 38%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 41% 9%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 58% 52%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 73% 21%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 88% 63%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 14% 79%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 46% 85%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 33% 66%, #ffffff1a 1.1px, transparent 1.6px), radial-gradient(circle at 67% 8%, #ffffff1a 1.1px, transparent 1.6px), radial-gradient(circle at 81% 42%, #ffffff1a 1.1px, transparent 1.6px), radial-gradient(circle at 95% 74%, #ffffff1a 1.1px, transparent 1.6px), radial-gradient(circle at 19% 24%, #ffffff1a 1.1px, transparent 1.6px)",
    "radial-gradient(circle at 6% 12%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 24% 38%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 41% 9%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 58% 52%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 73% 21%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 88% 63%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 14% 79%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 46% 85%, #ffffff29 1.6px, transparent 2.1px), radial-gradient(circle at 33% 66%, #ffffff1a 1.1px, transparent 1.6px), radial-gradient(circle at 67% 8%, #ffffff1a 1.1px, transparent 1.6px), radial-gradient(circle at 81% 42%, #ffffff1a 1.1px, transparent 1.6px), radial-gradient(circle at 95% 74%, #ffffff1a 1.1px, transparent 1.6px), radial-gradient(circle at 19% 24%, #ffffff1a 1.1px, transparent 1.6px)"
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
/** Ambient theme motion: reviewed animation shorthands only. Every keyframe moves or fades
 * the decorative pattern layer (transform/opacity), never text, layout or product colour. */
export const THEME_MOTIONS: ReadonlyMap<string, string> = new Map([
  ["float", "skin-float 9s ease-in-out infinite alternate"],
  ["breathe", "skin-breathe 7s ease-in-out infinite alternate"],
  ["twinkle", "skin-twinkle 2.8s ease-in-out infinite alternate"],
]);
/** Frame flourishes play a bounded number of times when the avatar appears. */
export const FRAME_MOTIONS: ReadonlySet<string> = new Set(["shine", "pulse", "orbit"]);
