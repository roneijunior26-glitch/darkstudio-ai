// Fundo 3D: nuvem de pontos em perspectiva + piso em grade, girando conforme o mouse (ou o toque / giroscópio).
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const cv = document.createElement("canvas");
cv.id = "bg3d";
document.body.prepend(cv);
const ctx = cv.getContext("2d");
let W = 0, H = 0, dpr = 1;
const N = innerWidth < 700 ? 70 : 140;
const pts = Array.from({ length: N }, () => ({
  x: (Math.random() - .5) * 2.6, y: (Math.random() - .5) * 1.6, z: (Math.random() - .5) * 2.6,
  c: Math.random() < .5 ? [34, 230, 208] : Math.random() < .5 ? [139, 92, 255] : [255, 79, 216],
  s: .6 + Math.random() * 1.6,
}));
let tx = 0, ty = 0, yaw = 0, pitch = 0, t0 = performance.now();
function size() {
  dpr = Math.min(devicePixelRatio || 1, 2);
  W = cv.width = innerWidth * dpr; H = cv.height = innerHeight * dpr;
  cv.style.width = innerWidth + "px"; cv.style.height = innerHeight + "px";
}
addEventListener("resize", size); size();
addEventListener("pointermove", e => { tx = e.clientX / innerWidth - .5; ty = e.clientY / innerHeight - .5; }, { passive: true });
addEventListener("deviceorientation", e => {
  if (e.gamma == null) return;
  tx = Math.max(-.5, Math.min(.5, e.gamma / 60)); ty = Math.max(-.5, Math.min(.5, (e.beta - 40) / 80));
}, { passive: true });

function project(x, y, z, f) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
  let X = x * cy - z * sy, Z = x * sy + z * cy;
  let Y = y * cp - Z * sp; Z = y * sp + Z * cp;
  const d = 2.4 + Z, k = f / d;
  return { px: W / 2 + X * k, py: H / 2 + Y * k, d, k };
}
function frame(now) {
  const t = (now - t0) / 1000;
  yaw += ((tx * 1.1 + (reduce ? 0 : Math.sin(t * .15) * .25)) - yaw) * .05;
  pitch += ((ty * .7 + .12) - pitch) * .05;
  ctx.clearRect(0, 0, W, H);
  const f = Math.min(W, H) * 1.05;
  // piso em grade (perspectiva)
  ctx.lineWidth = dpr;
  for (let i = -8; i <= 8; i++) {
    for (const [a, b] of [[[i * .35, 1.1, -2.8], [i * .35, 1.1, 2.8]], [[-2.8, 1.1, i * .35], [2.8, 1.1, i * .35]]]) {
      const p = project(...a, f), q = project(...b, f);
      const al = Math.max(0, .16 - Math.abs(i) * .012);
      ctx.strokeStyle = `rgba(80,140,255,${al})`;
      ctx.beginPath(); ctx.moveTo(p.px, p.py); ctx.lineTo(q.px, q.py); ctx.stroke();
    }
  }
  const P = pts.map(p => {
    const drift = reduce ? 0 : Math.sin(t * .4 + p.x * 3) * .04;
    return { ...project(p.x, p.y + drift, p.z, f), c: p.c, s: p.s };
  });
  // ligações entre pontos próximos
  for (let i = 0; i < P.length; i++) for (let j = i + 1; j < P.length; j++) {
    const dx = P[i].px - P[j].px, dy = P[i].py - P[j].py, dist = Math.hypot(dx, dy);
    const lim = 150 * dpr;
    if (dist < lim) {
      ctx.strokeStyle = `rgba(${P[i].c[0]},${P[i].c[1]},${P[i].c[2]},${(1 - dist / lim) * .22})`;
      ctx.beginPath(); ctx.moveTo(P[i].px, P[i].py); ctx.lineTo(P[j].px, P[j].py); ctx.stroke();
    }
  }
  P.sort((a, b) => b.d - a.d);
  for (const p of P) {
    const r = Math.max(.6, p.s * p.k * .0065) * dpr, a = Math.max(.15, Math.min(1, 1.6 - p.d * .35));
    const g = ctx.createRadialGradient(p.px, p.py, 0, p.px, p.py, r * 5);
    g.addColorStop(0, `rgba(${p.c[0]},${p.c[1]},${p.c[2]},${a})`); g.addColorStop(1, `rgba(${p.c[0]},${p.c[1]},${p.c[2]},0)`);
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.px, p.py, r * 5, 0, 6.283); ctx.fill();
  }
  if (!reduce && !document.hidden) requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
document.addEventListener("visibilitychange", () => { if (!document.hidden && !reduce) requestAnimationFrame(frame); });

// inclinação 3D + brilho que segue o mouse nos cartões
if (!reduce && matchMedia("(hover: hover)").matches) {
  const SEL = ".pcard,.stat,.card:not(.auth),.hero,.quick button";
  let cur = null;
  document.addEventListener("pointermove", e => {
    const el = e.target.closest?.(SEL);
    if (cur && cur !== el) { cur.style.removeProperty("--rx"); cur.style.removeProperty("--ry"); }
    cur = el;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
    const big = r.height > 260 ? .25 : 1; // cartões altos inclinam menos
    el.style.setProperty("--mx", (x * 100) + "%"); el.style.setProperty("--my", (y * 100) + "%");
    el.style.setProperty("--rx", ((.5 - y) * 5 * big).toFixed(2) + "deg"); el.style.setProperty("--ry", ((x - .5) * 6 * big).toFixed(2) + "deg");
  }, { passive: true });
  document.addEventListener("pointerleave", () => { if (cur) { cur.style.removeProperty("--rx"); cur.style.removeProperty("--ry"); } }, true);
}
