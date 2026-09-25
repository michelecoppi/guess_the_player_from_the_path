/**
 * Canvas particle celebration effect on correct guess.
 *
 * Every effect lasts two seconds, fades out over the last quarter and is skipped entirely
 * under prefers-reduced-motion. Simple effects are square particles described by a spec;
 * the richer ones (petals, pixels, comets, bubbles, flares, lightning, bounce) add their
 * own `spawn`/`draw` so the shape and the motion match the collection they belong to.
 */

export type CelebrationKind =
  | "spotlight"
  | "confetti"
  | "dust"
  | "flash"
  | "paper"
  | "snow"
  | "mud"
  | "fireworks"
  | "stadium_wave"
  | "petals"
  | "pixels"
  | "comets"
  | "bubbles"
  | "flares"
  | "lightning"
  | "bounce";

interface Particle {
  x: number;
  y: number;
  size: number;
  vx: number;
  vy: number;
  color: string;
  /** Free per-effect state: rotation, phase, a bolt's points... */
  spin: number;
  phase: number;
  points?: [number, number][];
}

interface CelebrationSpec {
  count: number;
  color: (i: number) => string;
  size: [number, number];
  fall: number;
  drift: number;
  /** Optional custom start position/velocity; defaults to the rain/rise behaviour. */
  spawn?: (bit: Particle, i: number, w: number, h: number, count: number) => void;
  /** Optional custom motion and drawing for one particle; `life` goes 0 -> 1. */
  draw?: (ctx: CanvasRenderingContext2D, bit: Particle, life: number, w: number, h: number) => void;
}

const rand = (min: number, max: number) => min + Math.random() * (max - min);

/** A jagged bolt from the top edge downwards. */
function bolt(w: number, h: number): [number, number][] {
  const points: [number, number][] = [];
  let x = rand(w * 0.15, w * 0.85);
  for (let y = 0; y < h * 0.72; y += rand(24, 52)) {
    points.push([x, y]);
    x += rand(-38, 38);
  }
  return points;
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
  stadium_wave: {
    count: 84, color: (i) => ["#ff824e", "#ffae74", "#f7d7b1"][i % 3], size: [4, 8], fall: -1.2, drift: 0,
    spawn: (bit, i, w, h, count) => { bit.x = (i / (count - 1)) * w; bit.y = h * (0.63 + (i % 3) * 0.035); },
    draw: (ctx, bit, life) => {
      bit.y += bit.vy;
      const crest = Math.sin(bit.x / 38 - life * 12) * 16;
      ctx.fillStyle = bit.color;
      ctx.fillRect(bit.x, bit.y + crest, bit.size, bit.size * 2);
    },
  },
  // Hanami: petals spin and sway as they fall.
  petals: {
    count: 60, color: (i) => ["#ff9ec7", "#ffd6e7", "#ff7fb0"][i % 3], size: [5, 10], fall: 1.6, drift: 0.8,
    draw: (ctx, bit, life) => {
      bit.y += bit.vy;
      bit.x += bit.vx + Math.sin(life * 9 + bit.phase) * 1.4;
      ctx.save();
      ctx.translate(bit.x, bit.y);
      ctx.rotate(bit.spin + life * 7);
      ctx.fillStyle = bit.color;
      ctx.beginPath();
      ctx.ellipse(0, 0, bit.size, bit.size * 0.55, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    },
  },
  // Arcade: 8-bit squares burst from the centre, fall under gravity and snap to a grid.
  pixels: {
    count: 64, color: (i) => ["#7cff4f", "#4f7cff", "#ff4fd8", "#ffe14f"][i % 4], size: [6, 12], fall: 0, drift: 0,
    spawn: (bit, _i, w, h) => {
      const angle = rand(0, Math.PI * 2), speed = rand(4, 11);
      bit.x = w / 2; bit.y = h * 0.45;
      bit.vx = Math.cos(angle) * speed; bit.vy = Math.sin(angle) * speed - 3;
    },
    draw: (ctx, bit) => {
      bit.vy += 0.32;
      bit.x += bit.vx;
      bit.y += bit.vy;
      const grid = 6;
      ctx.fillStyle = bit.color;
      ctx.fillRect(Math.round(bit.x / grid) * grid, Math.round(bit.y / grid) * grid, Math.round(bit.size / grid) * grid || grid, Math.round(bit.size / grid) * grid || grid);
    },
  },
  // Galaxy: comets cross diagonally with a fading tail.
  comets: {
    count: 16, color: (i) => ["#ffffff", "#b69cff", "#ffd98a", "#6fd0ff"][i % 4], size: [2, 4], fall: 0, drift: 0,
    spawn: (bit, _i, w, h) => {
      bit.x = rand(-w * 0.5, w * 0.7); bit.y = rand(-h * 0.5, h * 0.1);
      const speed = rand(9, 16);
      bit.vx = speed; bit.vy = speed * 0.62;
    },
    draw: (ctx, bit) => {
      bit.x += bit.vx;
      bit.y += bit.vy;
      const tail = ctx.createLinearGradient(bit.x, bit.y, bit.x - bit.vx * 9, bit.y - bit.vy * 9);
      tail.addColorStop(0, bit.color);
      tail.addColorStop(1, "transparent");
      ctx.strokeStyle = tail;
      ctx.lineWidth = bit.size;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(bit.x, bit.y);
      ctx.lineTo(bit.x - bit.vx * 9, bit.y - bit.vy * 9);
      ctx.stroke();
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(bit.x, bit.y, bit.size * 0.9, 0, Math.PI * 2);
      ctx.fill();
    },
  },
  // Beach: clear bubbles wobble upwards from the bottom.
  bubbles: {
    count: 46, color: () => "#bff4ff", size: [5, 16], fall: -2.2, drift: 0.3,
    spawn: (bit, _i, w, h) => { bit.x = rand(0, w); bit.y = h + rand(0, h * 0.4); },
    draw: (ctx, bit, life) => {
      bit.y += bit.vy;
      bit.x += Math.sin(life * 10 + bit.phase) * 0.9;
      ctx.strokeStyle = bit.color;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(bit.x, bit.y, bit.size, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = "rgba(255,255,255,.75)";
      ctx.beginPath();
      ctx.arc(bit.x - bit.size * 0.35, bit.y - bit.size * 0.35, bit.size * 0.22, 0, Math.PI * 2);
      ctx.fill();
    },
  },
  // Terrace: soft coloured smoke clouds rise and swell.
  flares: {
    count: 26, color: (i) => ["rgba(255,90,77,.20)", "rgba(255,241,236,.16)", "rgba(255,150,90,.18)"][i % 3], size: [26, 46], fall: -1.5, drift: 0.5,
    spawn: (bit, _i, w, h) => { bit.x = rand(-20, w + 20); bit.y = h + rand(-20, 80); },
    draw: (ctx, bit, life) => {
      bit.y += bit.vy;
      bit.x += bit.vx;
      const radius = bit.size * (1 + life * 1.8);
      const puff = ctx.createRadialGradient(bit.x, bit.y, 0, bit.x, bit.y, radius);
      puff.addColorStop(0, bit.color);
      puff.addColorStop(1, "transparent");
      ctx.fillStyle = puff;
      ctx.beginPath();
      ctx.arc(bit.x, bit.y, radius, 0, Math.PI * 2);
      ctx.fill();
    },
  },
  // Storm: one sky flash and two flickering bolts.
  lightning: {
    count: 2, color: () => "#fff38a", size: [3, 4], fall: 0, drift: 0,
    spawn: (bit, i, w, h) => { bit.points = bolt(w, h); bit.phase = i * 0.18; },
    draw: (ctx, bit, life, w, h) => {
      if (bit.phase === 0 && life < 0.12) {
        ctx.fillStyle = `rgba(214,236,255,${0.28 * (1 - life / 0.12)})`;
        ctx.fillRect(0, 0, w, h);
      }
      const t = life - bit.phase;
      if (t < 0 || t > 0.55 || Math.sin(t * 70) < -0.3) return;
      ctx.save();
      ctx.strokeStyle = bit.color;
      ctx.shadowColor = "#9fd3ff";
      ctx.shadowBlur = 18;
      ctx.lineWidth = bit.size;
      ctx.lineJoin = "round";
      ctx.beginPath();
      bit.points!.forEach(([x, y], index) => (index ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.stroke();
      ctx.restore();
    },
  },
  // Footballs drop and bounce off the bottom of the screen.
  bounce: {
    count: 14, color: () => "#ffffff", size: [22, 34], fall: 0, drift: 0,
    spawn: (bit, _i, w, h) => {
      bit.x = rand(20, w - 20); bit.y = rand(-h * 0.6, -20);
      bit.vx = rand(-2.2, 2.2); bit.vy = rand(0, 3);
    },
    draw: (ctx, bit, _life, w, h) => {
      bit.vy += 0.55;
      bit.x += bit.vx;
      bit.y += bit.vy;
      const floor = h - bit.size / 2 - 8;
      if (bit.y > floor) { bit.y = floor; bit.vy *= -0.68; }
      if (bit.x < 0 || bit.x > w) bit.vx *= -1;
      ctx.save();
      ctx.translate(bit.x, bit.y);
      ctx.rotate(bit.x / 30);
      ctx.font = `${Math.round(bit.size)}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("⚽", 0, 0);
      ctx.restore();
    },
  },
};

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
    const bit: Particle = {
      x: Math.random() * canvas.width,
      y: spec.fall >= 0 ? -Math.random() * canvas.height * 0.6 : canvas.height * (0.4 + Math.random() * 0.7),
      size: spec.size[0] + Math.random() * (spec.size[1] - spec.size[0]),
      vx: (Math.random() - 0.5) * spec.drift * 2,
      vy: spec.fall * (0.6 + Math.random()),
      color: spec.color(i),
      spin: Math.random() * Math.PI * 2,
      phase: Math.random() * Math.PI * 2,
    };
    spec.spawn?.(bit, i, canvas.width, canvas.height, spec.count);
    bits.push(bit);
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
      if (spec.draw) {
        spec.draw(ctx, bit, life, canvas.width, canvas.height);
        continue;
      }
      bit.x += bit.vx;
      bit.y += bit.vy;
      ctx.fillStyle = bit.color;
      ctx.fillRect(bit.x, bit.y, bit.size, bit.size);
    }
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
