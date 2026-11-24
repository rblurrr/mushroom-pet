import * as THREE from "./vendor/three.module.js";

export const PLACES = {
  plaza: { x: -5.4, z: 2.15, label: "The Plaza" },
  workshop: { x: -2.2, z: 3.6, label: "The Junction Box" },
  arcade: { x: 1.4, z: 5.0, label: "The Arcade" },
  library: { x: 5.0, z: 3.4, label: "The Library" },
  outlet_shop: { x: 7.0, z: 0.2, label: "The Outlet Shop" },
  laundromat: { x: 4.2, z: -3.0, label: "The Laundromat" },
  substation: { x: -4.4, z: -3.2, label: "The Substation" },
  notice: { x: 0.6, z: -0.6, label: "The Notice Pole" },
  kiosk: { x: 2.2, z: 1.0, label: "The Kiosk" },
  lines: { x: -1.0, z: 1.4, label: "The Lines" },
  last_pole: { x: 9.0, z: 2.4, label: "The Last Pole" },
};

const ORANGE = 0xf5841f;
const AMBER = 0xffb22e;
const INK = 0x141216;
const WHITE = 0xfff8f0;
const BLUSH = 0xffa6b0;
const TONGUE = 0xff7f92;
const SILVER = 0xb9bec6;
const BOLT = 0xffc531;
const MINT = 0x7fe0c9;
const PLUM = 0x2b1838;

function roundedRect(w, h, r) {
  const s = new THREE.Shape();
  const x = -w / 2;
  const y = -h / 2;
  const radius = Math.min(r, w / 2 - 0.001, h / 2 - 0.001);
  s.moveTo(x + radius, y);
  s.lineTo(x + w - radius, y);
  s.absarc(x + w - radius, y + radius, radius, -Math.PI / 2, 0, false);
  s.lineTo(x + w, y + h - radius);
  s.absarc(x + w - radius, y + h - radius, radius, 0, Math.PI / 2, false);
  s.lineTo(x + radius, y + h);
  s.absarc(x + radius, y + h - radius, radius, Math.PI / 2, Math.PI, false);
  s.lineTo(x, y + radius);
  s.absarc(x + radius, y + radius, radius, Math.PI, Math.PI * 1.5, false);
  return s;
}

function roundedBox(w, h, d, r) {
  const geo = new THREE.ExtrudeGeometry(roundedRect(w, h, r), {
    depth: d,
    bevelEnabled: true,
    bevelThickness: Math.min(r * 0.35, d * 0.18),
    bevelSize: Math.min(r * 0.28, 0.08),
    bevelSegments: 2,
    curveSegments: 6,
  });
  geo.translate(0, 0, -d / 2);
  geo.computeVertexNormals();
  return geo;
}

function paint(geo, topHex, bottomHex) {
  geo.computeBoundingBox();
  const box = geo.boundingBox;
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const top = new THREE.Color(topHex);
  const bottom = new THREE.Color(bottomHex);
  const span = box.max.y - box.min.y || 1;
  for (let i = 0; i < pos.count; i += 1) {
    const t = (pos.getY(i) - box.min.y) / span;
    const k = t < 0.34 ? t / 0.34 : 1;
    const color = bottom.clone().lerp(top, k);
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
}

function vinyl(geo) {
  paint(geo, ORANGE, AMBER);
  return new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
    vertexColors: true, roughness: 0.62, metalness: 0.02,
  }));
}

function mat(color, extra = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.7, metalness: 0.02, ...extra });
}

function basic(color, extra = {}) {
  return new THREE.MeshBasicMaterial({ color, ...extra });
}

function mesh(geo, material, x, y, z, parent) {
  const item = new THREE.Mesh(geo, material);
  item.position.set(x, y, z);
  item.castShadow = true;
  item.receiveShadow = true;
  if (parent) parent.add(item);
  return item;
}

function dShape(width) {
  const shape = new THREE.Shape();
  shape.moveTo(-width / 2, 0);
  shape.lineTo(width / 2, 0);
  shape.absarc(0, 0, width / 2, 0, Math.PI, true);
  return new THREE.ShapeGeometry(shape);
}

function makeSparky() {
  const root = new THREE.Group();
  const headGeo = roundedBox(1.05, 0.9, 0.84, 0.16);
  const head = vinyl(headGeo);
  head.position.set(0, 1.22, 0);
  root.add(head);

  const panel = mesh(
    roundedBox(0.84, 0.54, 0.08, 0.1),
    basic(WHITE),
    0, 1.14, 0.5, root,
  );

  const eyeGeo = new THREE.SphereGeometry(0.105, 18, 14);
  const eyes = new THREE.Group();
  const eyeMat = mat(INK, { roughness: 0.25 });
  const leftEye = mesh(eyeGeo, eyeMat, -0.2, 0.08, 0.05, eyes);
  const rightEye = mesh(eyeGeo, eyeMat, 0.2, 0.08, 0.05, eyes);
  const hi = basic(0xffffff);
  for (const eye of [leftEye, rightEye]) {
    mesh(new THREE.SphereGeometry(0.035, 10, 8), hi, -0.03, 0.035, 0.08, eye);
    mesh(new THREE.SphereGeometry(0.015, 8, 6), hi, 0.035, -0.03, 0.08, eye);
  }
  const happyEyes = new THREE.Group();
  const arc = new THREE.TorusGeometry(0.07, 0.02, 8, 16, Math.PI);
  mesh(arc, eyeMat, -0.2, 0.1, 0.06, happyEyes).rotation.z = Math.PI;
  mesh(arc, eyeMat, 0.2, 0.1, 0.06, happyEyes).rotation.z = Math.PI;
  happyEyes.visible = false;
  const sleepyEyes = new THREE.Group();
  mesh(arc, eyeMat, -0.2, 0.08, 0.06, sleepyEyes);
  mesh(arc, eyeMat, 0.2, 0.08, 0.06, sleepyEyes);
  sleepyEyes.visible = false;
  eyes.add(happyEyes, sleepyEyes);
  panel.add(eyes);

  const cheek = basic(BLUSH, { transparent: true, opacity: 0.6 });
  mesh(new THREE.SphereGeometry(0.055, 12, 10), cheek, -0.3, -0.08, 0.05, panel).scale.set(1.3, 0.8, 0.4);
  mesh(new THREE.SphereGeometry(0.055, 12, 10), cheek, 0.3, -0.08, 0.05, panel).scale.set(1.3, 0.8, 0.4);

  const mouths = new THREE.Group();
  mouths.position.set(0, -0.08, 0.06);
  const smile = mesh(dShape(0.18), basic(INK), 0, 0, 0, mouths);
  const tongue = mesh(new THREE.SphereGeometry(0.045, 10, 8), basic(TONGUE), 0, -0.035, 0.01, mouths);
  tongue.scale.set(1.1, 0.7, 0.4);
  const oh = mesh(new THREE.CircleGeometry(0.045, 16), basic(INK), 0, -0.02, 0, mouths);
  oh.visible = false;
  const flat = mesh(new THREE.BoxGeometry(0.1, 0.015, 0.01), basic(INK), 0, -0.01, 0, mouths);
  flat.visible = false;
  const zig = new THREE.Group();
  for (let i = 0; i < 4; i += 1) {
    mesh(new THREE.BoxGeometry(0.03, 0.012, 0.01), basic(INK), -0.05 + i * 0.034, (i % 2 ? 0.012 : -0.012), 0, zig);
  }
  zig.visible = false;
  mouths.add(zig);
  const talk = mesh(new THREE.CircleGeometry(0.055, 16), basic(INK), 0, -0.02, 0, mouths);
  talk.scale.set(1, 1.25, 1);
  talk.visible = false;
  const talkTongue = mesh(new THREE.SphereGeometry(0.03, 8, 6), basic(TONGUE), 0, -0.04, 0.01, mouths);
  talkTongue.visible = false;
  panel.add(mouths);

  const sweat = mesh(new THREE.SphereGeometry(0.035, 10, 8), basic(0x7fc8f8), 0.38, 0.12, 0.04, panel);
  sweat.scale.set(0.7, 1.3, 0.6);
  sweat.visible = false;
  const zzz = signTexture("z z z", "#5c4d70", "#fff8f0");
  zzz.position.set(0.42, 0.38, 0.2);
  zzz.scale.set(0.55, 0.28, 1);
  zzz.visible = false;
  head.add(zzz);

  const prongGeo = new THREE.CylinderGeometry(0.055, 0.055, 0.28, 16);
  const prongMat = mat(SILVER, { metalness: 0.72, roughness: 0.28 });
  const prongs = [
    mesh(prongGeo, prongMat, -0.32, 1.78, 0, root),
    mesh(prongGeo, prongMat, 0.32, 1.78, 0, root),
  ];
  for (const prong of prongs) {
    mesh(new THREE.SphereGeometry(0.055, 12, 8), prongMat, 0, 0.14, 0, prong);
  }

  const bolt = new THREE.Group();
  const boltMat = mat(BOLT, { roughness: 0.38 });
  const boltA = mesh(new THREE.BoxGeometry(0.2, 0.09, 0.1), boltMat, 0.02, 0.02, 0, bolt);
  const boltB = mesh(new THREE.BoxGeometry(0.2, 0.09, 0.1), boltMat, 0.05, 0.16, 0, bolt);
  const boltC = mesh(new THREE.BoxGeometry(0.16, 0.09, 0.1), boltMat, -0.01, 0.3, 0, bolt);
  boltA.rotation.z = -0.55;
  boltB.rotation.z = 0.65;
  boltC.rotation.z = -0.45;
  bolt.position.set(0.02, 1.68, 0);
  root.add(bolt);

  const body = vinyl(new THREE.SphereGeometry(0.34, 24, 18));
  body.scale.set(1, 1.15, 0.86);
  body.position.set(0, 0.58, 0);
  root.add(body);
  const arms = [-0.42, 0.42].map((x) => {
    const arm = vinyl(new THREE.SphereGeometry(0.13, 16, 12));
    arm.scale.set(0.85, 1.15, 0.8);
    arm.position.set(x, 0.5, 0.02);
    root.add(arm);
    return arm;
  });
  const legs = [-0.14, 0.14].map((x) => {
    const leg = new THREE.Group();
    const limb = vinyl(new THREE.CapsuleGeometry(0.07, 0.12, 4, 8));
    limb.position.y = 0.16;
    const foot = vinyl(new THREE.SphereGeometry(0.11, 16, 12));
    foot.scale.set(1.15, 0.72, 1.35);
    foot.position.set(0, 0.06, 0.03);
    leg.add(limb, foot);
    leg.position.set(x, 0.02, 0);
    root.add(leg);
    return leg;
  });

  const parts = { smile, tongue, oh, flat, zig, talk, talkTongue, happyEyes, sleepyEyes, leftEye, rightEye, sweat, zzz, eyes };

  function setExpression(name) {
    smile.visible = name === "neutral" || name === "happy";
    tongue.visible = name === "neutral" || name === "happy";
    smile.scale.setScalar(name === "happy" ? 1.18 : 1);
    oh.visible = name === "surprised";
    flat.visible = name === "sleepy";
    zig.visible = name === "nervous";
    talk.visible = name === "talking";
    talkTongue.visible = name === "talking";
    happyEyes.visible = name === "happy";
    sleepyEyes.visible = name === "sleepy";
    leftEye.visible = name !== "happy" && name !== "sleepy";
    rightEye.visible = leftEye.visible;
    sweat.visible = name === "nervous";
    zzz.visible = name === "sleepy";
    const shift = name === "nervous" ? 0.04 : 0;
    eyes.position.x = shift;
    const big = name === "surprised" ? 1.12 : 1;
    leftEye.scale.setScalar(big);
    rightEye.scale.setScalar(big);
  }

  function tick(time, moving) {
    if (moving) {
      root.position.y = Math.abs(Math.sin(time * 7.5)) * 0.045;
      body.rotation.z = Math.sin(time * 7.5) * 0.1;
      legs[0].rotation.x = Math.sin(time * 7.5) * 0.5;
      legs[1].rotation.x = Math.sin(time * 7.5 + Math.PI) * 0.5;
      arms[0].rotation.x = Math.sin(time * 7.5 + Math.PI) * 0.3;
      arms[1].rotation.x = Math.sin(time * 7.5) * 0.3;
    } else {
      root.position.y = Math.sin(time * 1.6) * 0.012;
      body.rotation.z = Math.sin(time * 1.3) * 0.03;
      legs[0].rotation.x = 0;
      legs[1].rotation.x = 0;
      arms[0].rotation.x = Math.sin(time * 1.3) * 0.05;
      arms[1].rotation.x = Math.sin(time * 1.3 + 0.4) * 0.05;
    }
  }

  setExpression("sleepy");
  return { root, head, setExpression, tick };
}

function signTexture(text, fg, bg) {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 128;
  const g = canvas.getContext("2d");
  g.fillStyle = bg;
  g.fillRect(0, 0, 256, 128);
  g.fillStyle = fg;
  g.font = "700 42px sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(text, 128, 64);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return new THREE.Mesh(new THREE.PlaneGeometry(1, 0.5), new THREE.MeshBasicMaterial({ map: texture, transparent: true }));
}

function building(w, h, d, color, x, y, z, parent) {
  const item = mesh(roundedBox(w, h, d, Math.min(0.18, w * 0.12)), mat(color), x, y, z, parent);
  return item;
}

function windowGlow(x, y, z, parent, color = 0xffd21f) {
  return mesh(new THREE.BoxGeometry(0.28, 0.34, 0.04), mat(color, { emissive: color, emissiveIntensity: 0.7 }), x, y, z, parent);
}

function pole(x, z, parent, height = 2.4) {
  const post = mesh(new THREE.CylinderGeometry(0.06, 0.07, height, 10), mat(PLUM), x, height / 2, z, parent);
  mesh(new THREE.SphereGeometry(0.09, 10, 8), mat(MINT, { emissive: MINT, emissiveIntensity: 0.4 }), x, height - 0.05, z, parent);
  return post;
}

function makeTown(scene) {
  const town = new THREE.Group();
  scene.add(town);
  const ground = mesh(new THREE.CircleGeometry(15, 48), mat(0xe4d4f2), 1.2, 0, 0.4, town);
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  const path = mesh(new THREE.RingGeometry(2.2, 6.4, 40), mat(0xd3c0e6), 1.2, 0.01, 0.4, town);
  path.rotation.x = -Math.PI / 2;

  building(2.4, 1.5, 1.6, 0x4a3068, -5.6, 0.75, -0.8, town);
  const canopy = mesh(new THREE.BoxGeometry(2.6, 0.08, 1.2), mat(0xffd21f, { emissive: 0xffd21f, emissiveIntensity: 0.25 }), -5.6, 1.7, 0.5, town);
  mesh(new THREE.CylinderGeometry(0.05, 0.05, 1.6, 8), mat(SILVER, { metalness: 0.5, roughness: 0.4 }), -6.4, 0.8, 0.5, town);
  mesh(new THREE.CylinderGeometry(0.05, 0.05, 1.6, 8), mat(SILVER, { metalness: 0.5, roughness: 0.4 }), -4.8, 0.8, 0.5, town);
  const cable = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-6.4, 1.55, 0.5),
    new THREE.Vector3(-5.6, 1.15, 0.7),
    new THREE.Vector3(-4.8, 1.55, 0.5),
  ]);
  mesh(new THREE.TubeGeometry(cable, 20, 0.025, 6, false), mat(INK), 0, 0, 0, town);
  const plazaSign = signTexture("PLAZA", "#2b1838", "#ffd21f");
  plazaSign.position.set(-5.6, 1.15, 0.05);
  town.add(plazaSign);

  const workshop = building(2.2, 1.7, 1.5, 0x3d2754, -2.4, 0.85, 4.3, town);
  windowGlow(-2.9, 1.0, 3.55, town);
  windowGlow(-1.9, 1.0, 3.55, town);
  const jar = new THREE.Group();
  jar.position.set(-1.5, 0.55, 3.5);
  mesh(new THREE.CylinderGeometry(0.16, 0.18, 0.42, 16), mat(0xd7fff4, { transparent: true, opacity: 0.45, roughness: 0.1 }), 0, 0.2, 0, jar);
  const sparks = [];
  for (let i = 0; i < 8; i += 1) {
    const bit = mesh(new THREE.SphereGeometry(0.035, 8, 6), mat(BOLT, { emissive: BOLT, emissiveIntensity: 0.8 }), (i % 3) * 0.06 - 0.06, 0.08 + Math.floor(i / 3) * 0.08, 0, jar);
    sparks.push(bit);
  }
  town.add(jar);

  building(1.8, 1.3, 1.2, 0x322046, 1.5, 0.65, 5.5, town);
  for (const x of [1.05, 1.5, 1.95]) {
    const cab = mesh(new THREE.BoxGeometry(0.32, 0.7, 0.28), mat(0x241433), x, 0.4, 4.85, town);
    mesh(new THREE.BoxGeometry(0.22, 0.18, 0.02), mat(MINT, { emissive: MINT, emissiveIntensity: 0.8 }), 0, 0.15, 0.15, cab);
  }

  building(2.0, 1.8, 1.3, 0x3a2450, 5.1, 0.9, 4.2, town);
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 4; col += 1) {
      const hue = [0xf5841f, 0x7fe0c9, 0xffd21f, 0xffa6b0][(row + col) % 4];
      mesh(new THREE.BoxGeometry(0.16, 0.28, 0.05), mat(hue), 4.45 + col * 0.22, 0.45 + row * 0.36, 3.55, town);
    }
  }

  const shop = building(2.1, 1.5, 0.4, 0x4a3068, 7.1, 0.75, -0.5, town);
  const sockets = [[-0.6, 0.3, 0.1], [-0.2, 0.35, 0.16], [0.25, 0.28, 0.08], [0.6, 0.4, 0.2]];
  sockets.forEach(([x, y, r], index) => {
    const geo = index === 1 ? new THREE.BoxGeometry(r * 2, r * 2.4, 0.04) : new THREE.CircleGeometry(r, 16);
    mesh(geo, mat(0x1a1024), x, y, 0.22, shop);
  });
  const nothing = signTexture("nothing fits", "#2b1838", "#fff8f0");
  nothing.position.set(7.1, 1.35, -0.2);
  town.add(nothing);

  building(2.2, 1.2, 1.4, 0x3a2450, 4.3, 0.6, -3.4, town);
  for (const x of [3.7, 4.3, 4.9]) {
    mesh(new THREE.CircleGeometry(0.22, 16), mat(0xffd21f, { emissive: 0xffd21f, emissiveIntensity: 0.55 }), x, 0.7, -2.68, town);
  }

  building(2.0, 1.4, 1.5, 0x241433, -4.5, 0.7, -4.0, town);
  mesh(new THREE.TorusGeometry(0.35, 0.04, 8, 20, Math.PI), mat(MINT, { emissive: MINT, emissiveIntensity: 0.9 }), -4.2, 1.3, -3.1, town);
  const fence = new THREE.Group();
  for (let i = 0; i < 5; i += 1) {
    mesh(new THREE.BoxGeometry(0.04, 0.7, 0.04), mat(SILVER, { metalness: 0.4 }), -5.3 + i * 0.4, 0.35, -2.5, fence);
  }
  mesh(new THREE.BoxGeometry(1.7, 0.04, 0.04), mat(SILVER, { metalness: 0.4 }), -4.5, 0.62, -2.5, fence);
  town.add(fence);

  pole(0.6, -0.2, town, 2.2);
  for (const y of [1.2, 1.45, 1.7]) {
    mesh(new THREE.BoxGeometry(0.22, 0.16, 0.02), mat(0xfff8f0), 0.75, y, -0.2, town);
  }
  pole(-1.2, 2.2, town, 2.6);
  pole(2.8, -1.2, town, 2.3);
  const wire = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-1.2, 2.5, 2.2),
    new THREE.Vector3(-0.2, 2.15, 0.8),
    new THREE.Vector3(0.6, 2.3, -0.2),
  ]);
  mesh(new THREE.TubeGeometry(wire, 24, 0.015, 5, false), mat(INK), 0, 0, 0, town);

  const kiosk = building(0.9, 1.1, 0.8, 0xffb22e, 2.3, 0.55, 1.3, town);
  const buzzer = mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.08, 12), mat(MINT, { emissive: MINT, emissiveIntensity: 0.2 }), 2.3, 1.15, 1.3, town);

  pole(9.0, 2.2, town, 3.1);
  const gateL = mesh(new THREE.BoxGeometry(0.08, 1.6, 0.08), mat(0x1a1024), 8.5, 0.8, 3.1, town);
  const gateR = mesh(new THREE.BoxGeometry(0.08, 1.6, 0.08), mat(0x1a1024), 9.5, 0.8, 3.1, town);
  mesh(new THREE.BoxGeometry(1.1, 0.08, 0.08), mat(0x1a1024), 9.0, 1.55, 3.1, town);

  const arc = new THREE.Group();
  mesh(new THREE.CapsuleGeometry(0.12, 0.55, 4, 8), mat(MINT, { roughness: 0.35 }), 0, 0.55, 0, arc);
  mesh(new THREE.SphereGeometry(0.14, 12, 10), mat(0xe8fff8), 0, 1.05, 0, arc);
  mesh(new THREE.SphereGeometry(0.03, 8, 6), basic(INK), -0.05, 1.08, 0.1, arc);
  mesh(new THREE.SphereGeometry(0.03, 8, 6), basic(INK), 0.05, 1.08, 0.1, arc);
  arc.position.set(-3.6, 0, -2.6);
  town.add(arc);

  const nutmeg = new THREE.Group();
  mesh(new THREE.SphereGeometry(0.16, 12, 10), mat(0x8c5a3c), 0, 0.16, 0, nutmeg);
  mesh(new THREE.SphereGeometry(0.1, 12, 10), mat(0xc4845a), 0.08, 0.28, 0.04, nutmeg);
  mesh(new THREE.SphereGeometry(0.08, 10, 8), mat(0x8c5a3c), -0.12, 0.2, -0.08, nutmeg);
  nutmeg.position.set(1.1, 0, -0.9);
  town.add(nutmeg);

  const hum = mesh(new THREE.CylinderGeometry(0.22, 0.26, 0.45, 12), mat(0x6d5480), -1.2, 1.7, 2.2, town);
  mesh(new THREE.SphereGeometry(0.03, 8, 6), basic(INK), -1.12, 1.75, 2.4, town);
  mesh(new THREE.SphereGeometry(0.03, 8, 6), basic(INK), -1.02, 1.75, 2.38, town);

  const frames = new THREE.Group();
  town.add(frames);

  const tv = new THREE.Group();
  tv.position.set(-2.2, 0.7, 2.35);
  mesh(roundedBox(1.15, 0.78, 0.12, 0.08), mat(PLUM), 0, 0, 0, tv);
  const screenMat = new THREE.MeshBasicMaterial({ color: 0xdccbea });
  const screen = mesh(new THREE.PlaneGeometry(0.96, 0.6), screenMat, 0, 0, 0.07, tv);
  mesh(new THREE.BoxGeometry(0.12, 0.5, 0.12), mat(PLUM), 0, -0.55, 0, tv);
  town.add(tv);

  const lights = [];
  [[-5.6, 1.2, 0.2], [0.6, 2.0, -0.2], [5, 1.4, 3.2], [-4.4, 1.5, -2.4]].forEach(([x, y, z]) => {
    const lamp = new THREE.PointLight(0xffd21f, 0.7, 7, 2);
    lamp.position.set(x, y, z);
    town.add(lamp);
    lights.push(lamp);
  });

  return { town, sparks, buzzer, gateL, gateR, frames, screen, screenMat, lights, canopy };
}

export function createWorld(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.12;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x2b1838);
  scene.fog = new THREE.Fog(0xd7c6ea, 12, 30);

  const skyGeo = new THREE.SphereGeometry(36, 28, 16);
  const skyPos = skyGeo.attributes.position;
  const skyColors = new Float32Array(skyPos.count * 3);
  const top = new THREE.Color(0x2b1838);
  const horizon = new THREE.Color(0xdccbea);
  for (let i = 0; i < skyPos.count; i += 1) {
    const k = THREE.MathUtils.clamp((skyPos.getY(i) + 8) / 28, 0, 1);
    const color = horizon.clone().lerp(top, Math.pow(k, 0.75));
    skyColors[i * 3] = color.r;
    skyColors[i * 3 + 1] = color.g;
    skyColors[i * 3 + 2] = color.b;
  }
  skyGeo.setAttribute("color", new THREE.BufferAttribute(skyColors, 3));
  const sky = new THREE.Mesh(skyGeo, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide, fog: false }));
  scene.add(sky);

  scene.add(new THREE.HemisphereLight(0xf4eef8, 0x2b1838, 0.85));
  const sun = new THREE.DirectionalLight(0xfff4e5, 1.25);
  sun.position.set(6, 10, 4);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 30;
  sun.shadow.camera.left = -12;
  sun.shadow.camera.right = 12;
  sun.shadow.camera.top = 12;
  sun.shadow.camera.bottom = -12;
  scene.add(sun);

  const town = makeTown(scene);
  const sparky = makeSparky();
  const shadow = mesh(new THREE.CircleGeometry(0.42, 20), basic(0x2b1838, { transparent: true, opacity: 0.18 }), 0, 0.02, 0, scene);
  shadow.rotation.x = -Math.PI / 2;
  scene.add(sparky.root);

  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 80);
  const target = new THREE.Vector3(PLACES.plaza.x, 0, PLACES.plaza.z);
  camera.position.set(PLACES.plaza.x + 1.2, 2.35, PLACES.plaza.z + 4.3);
  sparky.root.position.copy(target);
  let expression = "sleepy";
  let ar = false;
  let videoTexture = null;
  let flicker = false;
  let made = 1;

  function resize() {
    const width = canvas.clientWidth || window.innerWidth;
    const height = canvas.clientHeight || window.innerHeight;
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(1, height);
    camera.updateProjectionMatrix();
  }

  function setExpression(name) {
    expression = name || "neutral";
    sparky.setExpression(expression);
  }

  function setState(state) {
    const place = PLACES[state.place] || PLACES.plaza;
    target.set(place.x, 0, place.z);
    setExpression(state.expression);
    const count = Math.max(0, Math.min(8, Math.round((state.jar?.count || 0) / 12.5)));
    town.sparks.forEach((bit, index) => { bit.visible = index < count; });
    const open = !!state.kiosk_open;
    town.buzzer.material.emissiveIntensity = open ? 0.9 : 0.05;
    const dark = !state.jar?.dark_blocks;
    town.gateL.material.color.set(dark ? 0x1a1024 : 0x7fe0c9);
    town.gateR.material.color.set(dark ? 0x1a1024 : 0x7fe0c9);
    flicker = !!state.morph?.flicker;
    if (scene.fog) {
      scene.fog.near = state.morph?.fog ? 4 : 12;
      scene.fog.far = state.morph?.fog ? 14 : 30;
    }
    const nextMade = (state.made || []).length;
    if (nextMade !== made) {
      made = nextMade;
      town.frames.clear();
      (state.made || []).slice(0, 4).forEach((item, index) => {
        const frame = signTexture(item.title.slice(0, 18), "#2b1838", "#fff8f0");
        frame.position.set(-3.1, 0.7 + (index % 2) * 0.45, 3.5 + Math.floor(index / 2) * 0.05);
        frame.scale.set(0.7, 0.7, 0.7);
        town.frames.add(frame);
      });
    }
  }

  function setVideo(video) {
    if (videoTexture) {
      videoTexture.dispose();
      videoTexture = null;
    }
    if (!video) {
      town.screen.material = town.screenMat;
      return;
    }
    videoTexture = new THREE.VideoTexture(video);
    videoTexture.colorSpace = THREE.SRGBColorSpace;
    town.screen.material = new THREE.MeshBasicMaterial({ map: videoTexture });
  }

  function setAR(on) {
    ar = !!on;
    sky.visible = !ar;
    scene.background = ar ? null : new THREE.Color(0x2b1838);
    town.town.visible = !ar;
    scene.fog = ar ? null : new THREE.Fog(0xd7c6ea, 12, 30);
    renderer.setClearColor(0x000000, ar ? 0 : 1);
  }

  function headScreen() {
    const point = new THREE.Vector3(0, 1.85, 0);
    sparky.root.localToWorld(point);
    point.project(camera);
    const width = canvas.clientWidth || window.innerWidth;
    const height = canvas.clientHeight || window.innerHeight;
    return {
      x: (point.x * 0.5 + 0.5) * width,
      y: (-point.y * 0.5 + 0.5) * height,
      behind: point.z > 1,
    };
  }

  function frame(now) {
    requestAnimationFrame(frame);
    const time = now / 1000;
    const dx = target.x - sparky.root.position.x;
    const dz = target.z - sparky.root.position.z;
    const dist = Math.hypot(dx, dz);
    const moving = dist > 0.04;
    if (moving) {
      const step = Math.min(0.012, dist);
      sparky.root.position.x += (dx / dist) * step;
      sparky.root.position.z += (dz / dist) * step;
      sparky.root.rotation.y = Math.atan2(dx, dz);
    } else {
      const face = Math.atan2(camera.position.x - sparky.root.position.x, camera.position.z - sparky.root.position.z);
      sparky.root.rotation.y += (face - sparky.root.rotation.y) * 0.04;
    }
    sparky.tick(time, moving);
    shadow.position.x = sparky.root.position.x;
    shadow.position.z = sparky.root.position.z;
    if (flicker) {
      town.lights.forEach((lamp, index) => {
        lamp.intensity = 0.25 + Math.abs(Math.sin(time * 8 + index)) * 0.9;
      });
    }
    const look = sparky.root.position;
    const desired = new THREE.Vector3(look.x + 1.2, look.y + 1.25, look.z + 4.3);
    camera.position.lerp(desired, 0.08);
    camera.lookAt(look.x - 0.35, look.y + 0.82, look.z);
    renderer.render(scene, camera);
  }

  resize();
  window.addEventListener("resize", resize);
  requestAnimationFrame(frame);
  return { setState, setExpression, setVideo, setAR, headScreen, resize, places: PLACES };
}
