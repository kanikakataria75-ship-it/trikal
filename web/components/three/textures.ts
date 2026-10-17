import * as THREE from "three";

/* Procedural textures for the touchstone (no downloaded assets).
   A real kasauti is black basalt / slate, polished, covered in faint old test streaks. */

function hash(x: number, y: number, s: number) {
  const h = Math.sin(x * 127.1 + y * 311.7 + s * 74.7) * 43758.5453;
  return h - Math.floor(h);
}

function valueNoise(x: number, y: number, s: number) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = hash(xi, yi, s), b = hash(xi + 1, yi, s), c = hash(xi, yi + 1, s), d = hash(xi + 1, yi + 1, s);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}

function fbm(x: number, y: number, oct: number, s: number) {
  let f = 0, amp = 0.5, fr = 1;
  for (let i = 0; i < oct; i++) { f += amp * valueNoise(x * fr, y * fr, s + i); fr *= 2.03; amp *= 0.5; }
  return f;
}

export function makeStoneTextures(size = 512) {
  const height = new Float32Array(size * size);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const nx = x / size, ny = y / size;
      // basalt: fine grain + soft mottling + a few hairline veins
      const grain = fbm(nx * 90, ny * 90, 3, 1);
      const mott = fbm(nx * 6, ny * 6, 4, 7);
      const vein = Math.pow(1 - Math.abs(Math.sin((nx * 3.1 + fbm(nx * 4, ny * 4, 3, 3) * 2.2) * Math.PI)), 28);
      height[y * size + x] = grain * 0.55 + mott * 0.35 + vein * 0.25;
    }

  // colour: near-black with mottling and faint old streak scars
  const cc = document.createElement("canvas");
  cc.width = cc.height = size;
  const cx = cc.getContext("2d")!;
  const img = cx.createImageData(size, size);
  for (let i = 0; i < size * size; i++) {
    const h = height[i];
    const v = 7 + h * 16;
    img.data[i * 4] = v; img.data[i * 4 + 1] = v * 1.01; img.data[i * 4 + 2] = v * 1.08; img.data[i * 4 + 3] = 255;
  }
  cx.putImageData(img, 0, 0);
  // old rubbings from earlier assays: faint, scratchy, mostly worn away
  let seed = 11;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let k = 0; k < 46; k++) {
    const x0 = rnd() * size, y0 = rnd() * size, len = 40 + rnd() * 160, ang = (rnd() - 0.5) * 0.5;
    const gold = rnd() > 0.55;
    for (let j = 0; j < 30; j++) {
      cx.strokeStyle = gold ? `rgba(160,130,60,${0.025 + rnd() * 0.05})` : `rgba(120,120,125,${0.02 + rnd() * 0.04})`;
      cx.lineWidth = 0.5 + rnd() * 1.4;
      const oy = (rnd() - 0.5) * 7;
      cx.beginPath();
      cx.moveTo(x0, y0 + oy);
      cx.lineTo(x0 + Math.cos(ang) * len * (0.6 + rnd() * 0.4), y0 + oy + Math.sin(ang) * len);
      cx.stroke();
    }
  }
  const map = new THREE.CanvasTexture(cc);
  map.colorSpace = THREE.SRGBColorSpace;
  map.anisotropy = 8;

  // roughness: polished but uneven (worn centre is glossier)
  const rc = document.createElement("canvas");
  rc.width = rc.height = size;
  const rx = rc.getContext("2d")!;
  const rimg = rx.createImageData(size, size);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const i = y * size + x;
      const dx = x / size - 0.5, dy = y / size - 0.5;
      const wear = Math.sqrt(dx * dx + dy * dy) * 0.5;
      const r = 0.16 + wear * 0.35 + height[i] * 0.22;
      const v = Math.min(255, r * 255);
      rimg.data[i * 4] = v; rimg.data[i * 4 + 1] = v; rimg.data[i * 4 + 2] = v; rimg.data[i * 4 + 3] = 255;
    }
  rx.putImageData(rimg, 0, 0);
  const roughness = new THREE.CanvasTexture(rc);

  // normal map from the height field (Sobel)
  const nc = document.createElement("canvas");
  nc.width = nc.height = size;
  const nx2 = nc.getContext("2d")!;
  const nimg = nx2.createImageData(size, size);
  const H = (x: number, y: number) => height[((y + size) % size) * size + ((x + size) % size)];
  const strength = 2.2;
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const dx = (H(x + 1, y - 1) + 2 * H(x + 1, y) + H(x + 1, y + 1) - H(x - 1, y - 1) - 2 * H(x - 1, y) - H(x - 1, y + 1)) * strength;
      const dy = (H(x - 1, y + 1) + 2 * H(x, y + 1) + H(x + 1, y + 1) - H(x - 1, y - 1) - 2 * H(x, y - 1) - H(x + 1, y - 1)) * strength;
      const len = Math.hypot(dx, dy, 1);
      const i = (y * size + x) * 4;
      nimg.data[i] = ((-dx / len) * 0.5 + 0.5) * 255;
      nimg.data[i + 1] = ((-dy / len) * 0.5 + 0.5) * 255;
      nimg.data[i + 2] = (1 / len) * 255;
      nimg.data[i + 3] = 255;
    }
  nx2.putImageData(nimg, 0, 0);
  const normal = new THREE.CanvasTexture(nc);
  return { map, roughness, normal };
}

/* Organic slab: a rounded box whose vertices are pushed by low-frequency noise (hand-cut stone, not CAD). */
export function organicSlab(geo: THREE.BufferGeometry, amount = 0.035, seed = 3) {
  const p = geo.attributes.position as THREE.BufferAttribute;
  const v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    const n = fbm(v.x * 0.9 + 10, v.z * 0.9 + 4, 3, seed) - 0.5;
    const m = fbm(v.x * 2.3, v.y * 2.3 + v.z, 2, seed + 9) - 0.5;
    const top = v.y > 0 ? 0.35 : 1; // keep the assay face flatter
    v.x += m * amount * 0.6;
    v.z += n * amount * 0.8;
    v.y += (n * 0.6 + m * 0.4) * amount * top;
    p.setXYZ(i, v.x, v.y, v.z);
  }
  geo.computeVertexNormals();
  return geo;
}
