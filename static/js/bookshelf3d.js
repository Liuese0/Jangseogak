// ══════════════════════════════════════════════════════
// 장서각 — 3D 책장 · KNU Edition (GLB model + horizontal label)
// ══════════════════════════════════════════════════════

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const KNU_BLUE = 0x1d4e9a;
const KNU_ORANGE = 0xef6c1f;
const KNU_WHITE = 0xf7f9fc;

const MODEL_URL = new URL('../models/white_book.glb', import.meta.url).href;

const canvas = document.getElementById('bookshelf3d');
const tooltip = document.getElementById('bookTooltip');
const container = document.getElementById('bookshelf3dContainer');
const statusEl = document.getElementById('bookshelfStatus');

// ── GLB template cache ──
let _bookTemplate = null;
const _loader = new GLTFLoader();

function loadBookTemplate() {
  if (_bookTemplate) return Promise.resolve(_bookTemplate);
  return new Promise((resolve, reject) => {
    _loader.load(
      MODEL_URL,
      (gltf) => {
        const root = gltf.scene;
        const box = new THREE.Box3().setFromObject(root);
        const size = new THREE.Vector3(); box.getSize(size);
        const center = new THREE.Vector3(); box.getCenter(center);
        root.position.sub(center);
        root.updateMatrixWorld(true);
        _bookTemplate = { root, size: size.clone(), center: center.clone() };
        resolve(_bookTemplate);
      },
      undefined,
      reject
    );
  });
}

if (!canvas || !window.BOOKSHELF_DATA || window.BOOKSHELF_DATA.length === 0) {
  if (container) container.style.display = 'none';
} else {
  (async () => {
    try {
      const testCtx = canvas.getContext('webgl2') || canvas.getContext('webgl');
      if (!testCtx) throw new Error('WebGL not supported');
      if (statusEl) statusEl.textContent = '3D 모델 로딩 중…';
      await initBookshelf(window.BOOKSHELF_DATA);
      if (statusEl) statusEl.style.display = 'none';
    } catch (e) {
      console.error('[bookshelf3d] init error:', e);
      if (statusEl) statusEl.textContent = '3D 초기화 실패: ' + e.message;
    }
  })();
}

async function initBookshelf(books) {
  // ── Scene ──
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(KNU_WHITE);
  scene.fog = new THREE.Fog(KNU_WHITE, 10, 22);

  // ── Camera ──
  const camera = new THREE.PerspectiveCamera(
    38,
    canvas.clientWidth / Math.max(canvas.clientHeight, 1),
    0.1, 100
  );
  camera.position.set(0, 2.0, 7.2);
  camera.lookAt(0, 0.3, 0);

  // ── Renderer ──
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.LinearToneMapping;
  renderer.toneMappingExposure = 1.1;

  // ── Clean studio lighting ──
  scene.add(new THREE.AmbientLight(0xffffff, 0.85));

  const keyLight = new THREE.DirectionalLight(0xffffff, 1.1);
  keyLight.position.set(4, 8, 5);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(2048, 2048);
  keyLight.shadow.camera.left = -6;
  keyLight.shadow.camera.right = 6;
  keyLight.shadow.camera.top = 6;
  keyLight.shadow.camera.bottom = -6;
  keyLight.shadow.bias = -0.0005;
  keyLight.shadow.radius = 6;
  scene.add(keyLight);

  const rimLight = new THREE.DirectionalLight(0xcfe0ff, 0.55);
  rimLight.position.set(-5, 3, -4);
  scene.add(rimLight);

  const fillLight = new THREE.DirectionalLight(0xffffff, 0.35);
  fillLight.position.set(0, 1, 6);
  scene.add(fillLight);

  // ── Floor ──
  const floorGeo = new THREE.CircleGeometry(7, 96);
  const floorMat = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    roughness: 0.4,
    metalness: 0.05,
  });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -1.25;
  floor.receiveShadow = true;
  scene.add(floor);

  addRing(scene, 3.6, 3.65, KNU_BLUE, 0.8);
  addRing(scene, 3.95, 3.97, KNU_BLUE, 0.8);

  const dotGeo = new THREE.BoxGeometry(0.15, 0.02, 0.15);
  const dotMat = new THREE.MeshStandardMaterial({
    color: KNU_ORANGE, roughness: 0.4, metalness: 0.2,
  });
  const dot = new THREE.Mesh(dotGeo, dotMat);
  dot.rotation.y = Math.PI / 4;
  dot.position.set(3.8, -1.235, 0);
  scene.add(dot);

  // ── Dome ──
  const domeGeo = new THREE.SphereGeometry(16, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2);
  const domeMat = new THREE.MeshBasicMaterial({
    map: makeDomeTexture(),
    side: THREE.BackSide,
    fog: false,
  });
  const dome = new THREE.Mesh(domeGeo, domeMat);
  dome.position.y = -1.25;
  scene.add(dome);

  // ── Load book template (await GLB) ──
  await loadBookTemplate();

  // ── Book carousel ──
  const carousel = new THREE.Group();
  scene.add(carousel);

  const BASE_HEIGHT = 2.0;
  const RADIUS = 2.9;

  const { size: tplSize } = _bookTemplate;
  // Figure out which axis of the template is the longest (spine / standing axis)
  // Most "book" models are oriented with Y as vertical; if not, this will still
  // produce consistent scaling because we normalize on Y.
  const holders = [];

  books.forEach((book, i) => {
    const angle = (i / books.length) * Math.PI * 2;
    const heightJitter = 0.9 + ((hashStr(book.title) % 100) / 100) * 0.2;
    const h = BASE_HEIGHT * heightJitter;

    // Instantiate a book
    const bookInstance = instantiateBook();
    const bookScale = h / tplSize.y;
    bookInstance.scale.setScalar(bookScale);

    // Attach horizontal label on the front face (+Z of template, inside local space)
    attachLabel(bookInstance, book, tplSize, bookScale);

    // Holder handles ring position + outward rotation + entrance animation
    const holder = new THREE.Group();
    holder.position.x = Math.cos(angle) * RADIUS;
    holder.position.z = Math.sin(angle) * RADIUS;
    const finalY = (h - BASE_HEIGHT) / 2;
    holder.rotation.y = -angle + Math.PI / 2;
    holder.add(bookInstance);

    // Entrance animation state
    holder.userData = {
      book,
      hovered: false,
      baseY: finalY,
      anim: {
        delay: i * 0.08,
        duration: 1.2,
        startY: finalY - 1.6,
        endY: finalY,
        startScale: 0.001,
        endScale: 1.0,
        done: false,
      },
    };
    // Initial state (below floor, invisible, tiny)
    holder.position.y = holder.userData.anim.startY;
    holder.scale.setScalar(0.001);
    holder.traverse((o) => {
      if (o.isMesh && o.material) {
        o.material.transparent = true;
        o.material.opacity = 0;
      }
    });

    carousel.add(holder);
    holders.push(holder);
  });

  // ── Controls ──
  const controls = new OrbitControls(camera, canvas);
  controls.enableZoom = false;
  controls.enablePan = false;
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.5;
  controls.minPolarAngle = Math.PI / 3.2;
  controls.maxPolarAngle = Math.PI / 2.15;
  controls.target.set(0, 0.4, 0);

  // ── Interaction ──
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  let hoveredHolder = null;
  let idleTimer = null;

  function resolveHolder(obj) {
    let h = obj;
    while (h && !h.userData?.book) h = h.parent;
    return h;
  }

  function onPointerMove(event) {
    const rect = canvas.getBoundingClientRect();
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    const hits = raycaster.intersectObjects(holders, true);
    if (hits.length > 0) {
      const holder = resolveHolder(hits[0].object);
      if (holder && hoveredHolder !== holder) {
        if (hoveredHolder) hoveredHolder.userData.hovered = false;
        hoveredHolder = holder;
        holder.userData.hovered = true;
        canvas.style.cursor = 'pointer';
        if (tooltip) {
          tooltip.textContent = `${holder.userData.book.title} — ${holder.userData.book.author}`;
          tooltip.style.opacity = '1';
        }
      }
      if (tooltip) {
        tooltip.style.left = (event.clientX - rect.left + 12) + 'px';
        tooltip.style.top = (event.clientY - rect.top + 12) + 'px';
      }
    } else {
      if (hoveredHolder) { hoveredHolder.userData.hovered = false; hoveredHolder = null; }
      canvas.style.cursor = 'grab';
      if (tooltip) tooltip.style.opacity = '0';
    }
  }

  function onClick() {
    if (hoveredHolder && hoveredHolder.userData.book) {
      window.location.href = `/book/${hoveredHolder.userData.book.id}`;
    }
  }

  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('click', onClick);
  canvas.addEventListener('pointerdown', () => {
    controls.autoRotate = false;
    if (idleTimer) clearTimeout(idleTimer);
  });
  canvas.addEventListener('pointerup', () => {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { controls.autoRotate = true; }, 4000);
  });
  canvas.addEventListener('pointerleave', () => {
    if (hoveredHolder) hoveredHolder.userData.hovered = false;
    hoveredHolder = null;
    if (tooltip) tooltip.style.opacity = '0';
  });

  // ── Resize ──
  function onResize() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', onResize);
  onResize();

  // ── Animate ──
  const clock = new THREE.Clock();
  const startT = clock.getElapsedTime();

  function animate() {
    requestAnimationFrame(animate);
    const t = clock.getElapsedTime();

    holders.forEach((holder, i) => {
      const a = holder.userData.anim;
      if (!a.done) {
        updateEntrance(holder, t - startT);
        return;
      }
      const baseY = holder.userData.baseY;
      const target = holder.userData.hovered
        ? baseY + 0.26
        : baseY + Math.sin(t * 0.6 + i) * 0.006;
      holder.position.y += (target - holder.position.y) * 0.15;
    });

    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}

// ── Instantiate a book from the cached template ──
function instantiateBook() {
  const clone = _bookTemplate.root.clone(true);
  clone.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
      o.material = o.material.clone();
    }
  });
  return clone;
}

// ── Horizontal label plane attached to the book's +Z face ──
function attachLabel(bookRoot, book, size) {
  const labelW = size.x * 0.78;
  const labelH = size.y * 0.30;
  const geo = new THREE.PlaneGeometry(labelW, labelH);
  const mat = new THREE.MeshStandardMaterial({
    map: makeLabelTexture(book.title, book.author),
    transparent: true,
    roughness: 0.85,
    metalness: 0.0,
    depthWrite: false,
  });
  const label = new THREE.Mesh(geo, mat);
  label.position.set(0, 0, size.z * 0.51);
  label.renderOrder = 2;
  label.userData.isLabel = true;
  bookRoot.add(label);
  return label;
}

// ── Horizontal text texture (title + author, no rotation) ──
function makeLabelTexture(title, author) {
  const W = 512, H = 192;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, W, H);

  ctx.fillStyle = '#1d4e9a';
  ctx.font = "700 56px 'IBM Plex Sans', 'Noto Sans KR', sans-serif";
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  let t = title;
  while (ctx.measureText(t + '…').width > W - 40 && t.length > 1) {
    t = t.slice(0, -1);
  }
  if (t !== title) t += '…';
  ctx.fillText(t, W / 2, H / 2 - 18);

  if (author) {
    ctx.font = "400 28px 'IBM Plex Sans', 'Noto Sans KR', sans-serif";
    ctx.fillStyle = '#444';
    let a = author;
    while (ctx.measureText(a).width > W - 60 && a.length > 1) {
      a = a.slice(0, -1);
    }
    ctx.fillText(a, W / 2, H / 2 + 34);
  }

  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 8;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

// ── Entrance animation driver ──
function easeOutCubic(x) { return 1 - Math.pow(1 - x, 3); }

function updateEntrance(holder, elapsed) {
  const a = holder.userData.anim;
  if (a.done) return;
  const local = Math.min(Math.max((elapsed - a.delay) / a.duration, 0), 1);
  const k = easeOutCubic(local);
  holder.position.y = a.startY + (a.endY - a.startY) * k;
  holder.scale.setScalar(a.startScale + (a.endScale - a.startScale) * k);
  holder.traverse((o) => {
    if (o.isMesh && o.material) o.material.opacity = k;
  });
  if (local >= 1) {
    a.done = true;
    holder.userData.baseY = a.endY;
    holder.traverse((o) => {
      if (o.isMesh && o.material && !o.userData.isLabel) {
        o.material.transparent = false;
        o.material.opacity = 1;
      }
    });
  }
}

// ── Ring helper ──
function addRing(scene, inner, outer, colorHex, opacity) {
  const geo = new THREE.RingGeometry(inner, outer, 128);
  const mat = new THREE.MeshBasicMaterial({
    color: colorHex,
    transparent: true,
    opacity,
    side: THREE.DoubleSide,
    fog: false,
  });
  const ring = new THREE.Mesh(geo, mat);
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = -1.24;
  scene.add(ring);
  return ring;
}

// ── Dome backdrop: soft white→pale blue gradient ──
function makeDomeTexture() {
  const W = 1024, H = 512;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#e8eef8');
  g.addColorStop(0.5, '#f3f6fb');
  g.addColorStop(1, '#fdfefe');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}
