/**
 * Canvas particle celebration effect on correct guess.
 * Exactly matches the visual experience of legacy webapp/index.html.
 */

export type CelebrationKind =
  | "spotlight"
  | "confetti"
  | "dust"
  | "flash"
  | "paper"
  | "snow"
  | "mud"
  | "fireworks";

interface CelebrationSpec {
  count: number;
  color: (i: number) => string;
  size: [number, number];
  fall: number;
  drift: number;
}

const CELEBRATIONS: Record<string, CelebrationSpec> = {
  spotlight: { count: 26, color: () => "#fff6d5", size: [3, 9], fall: -0.4, drift: 0 },
  confetti: {
    count: 90,
    color: (i) => ["#ff5a5a", "#3ddc84", "#4dc4ff", "#ffd028"][i % 4],
    size: [4, 10],
    fall: 2.4,
    drift: 1.2,
  },
  dust: { count: 60, color: () => "#c9bfa4", size: [2, 6], fall: -0.8, drift: 0.6 },
  flash: { count: 18, color: () => "#ffffff", size: [6, 16], fall: 0, drift: 0 },
  paper: { count: 70, color: () => "#f3ecd8", size: [5, 13], fall: 2.0, drift: 1.6 },
  snow: { count: 80, color: () => "#eaf6ff", size: [2, 6], fall: 1.1, drift: 0.8 },
  mud: { count: 55, color: (i) => ["#6b5a3a", "#9aa861"][i % 2], size: [3, 9], fall: 2.6, drift: 0.9 },
  fireworks: { count: 70, color: (i) => ["#f2c74c", "#7fc4ff", "#ff9ce3"][i % 3], size: [3, 8], fall: -1.4, drift: 1.4 },
};

interface Particle {
  x: number;
  y: number;
  size: number;
  vx: number;
  vy: number;
  color: string;
}

export function celebrate(effect?: string | null): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const kind = effect && Object.hasOwn(CELEBRATIONS, effect) ? effect : "";
  const spec = CELEBRATIONS[kind];
  if (!spec) return;

  const canvas = document.createElement("canvas");
  canvas.className = "celebration";
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  document.body.appendChild(canvas);

  const ctx = canvas.getContext("2d");
  if (!ctx) {
    canvas.remove();
    return;
  }

  const bits: Particle[] = [];
  for (let i = 0; i < spec.count; i++) {
    bits.push({
      x: Math.random() * canvas.width,
      y: spec.fall >= 0 ? -Math.random() * canvas.height * 0.6 : canvas.height * (0.4 + Math.random() * 0.7),
      size: spec.size[0] + Math.random() * (spec.size[1] - spec.size[0]),
      vx: (Math.random() - 0.5) * spec.drift * 2,
      vy: spec.fall * (0.6 + Math.random()),
      color: spec.color(i),
    });
  }

  const started = performance.now();
  const step = (now: number) => {
    const life = (now - started) / 2000;
    if (life >= 1) {
      canvas.remove();
      return;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.globalAlpha = life < 0.75 ? 1 : (1 - life) * 4;
    for (const bit of bits) {
      bit.x += bit.vx;
      bit.y += bit.vy;
      ctx.fillStyle = bit.color;
      ctx.fillRect(bit.x, bit.y, bit.size, bit.size);
    }
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
