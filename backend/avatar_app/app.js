// app.js
alert('app.js malla de puntos dinámica + sombreado por textura está cargando');

import * as THREE from 'three';
import { GLTFLoader } from 'https://cdn.jsdelivr.net/npm/three@0.160/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'https://cdn.jsdelivr.net/npm/three@0.160/examples/jsm/controls/OrbitControls.js';
import * as BufferGeometryUtils from 'https://cdn.jsdelivr.net/npm/three@0.160/examples/jsm/utils/BufferGeometryUtils.js';

// =========================
// 1. Escena básica
// =========================
const canvas = document.getElementById('c');

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);

const camera = new THREE.PerspectiveCamera(
  40,
  window.innerWidth / window.innerHeight,
  0.01,
  100
);
camera.position.set(0, 0.25, 1.9);

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true
});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.target.set(0, 0.2, 0);

const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
keyLight.position.set(2, 4, 3);
scene.add(keyLight);

const rimLight = new THREE.DirectionalLight(0xffffff, 0.5);
rimLight.position.set(-2, 3, -2);
scene.add(rimLight);

const ambient = new THREE.AmbientLight(0xffffff, 0.2);
scene.add(ambient);

const clock = new THREE.Clock();

// =========================
// Config boca (ajustable a mano)
// =========================
const MOUTH_CENTER_Y = 0.16;     // posición vertical del centro de la boca
const MOUTH_CENTER_X = -0.045;  // posición horizontal del centro de la boca
const MOUTH_WIDTH    = 0.18;    // ancho de la región de boca
const MOUTH_HEIGHT   = 0.20;    // alto máximo (labios + hueco)
const MOUTH_CURVE    = 0.0;     // curvatura en U (0 = recto)

// =========================
// Control "Hablar" (botón)
// =========================
let isTalking = false;

const talkButton = document.createElement('button');
talkButton.textContent = 'Hablar (mantén)';
Object.assign(talkButton.style, {
  position: 'fixed',
  bottom: '20px',
  left: '50%',
  transform: 'translateX(-50%)',
  padding: '10px 22px',
  borderRadius: '999px',
  border: 'none',
  background: 'rgba(255,255,255,0.14)',
  color: '#ffffff',
  fontFamily:
    'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  fontSize: '13px',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  cursor: 'pointer',
  backdropFilter: 'blur(12px)',
  zIndex: '10'
});
document.body.appendChild(talkButton);

const startTalking = () => {
  isTalking = true;
};
const stopTalking = () => {
  isTalking = false;
};

talkButton.addEventListener('mousedown', startTalking);
talkButton.addEventListener('mouseup', stopTalking);
talkButton.addEventListener('mouseleave', stopTalking);

talkButton.addEventListener(
  'touchstart',
  (e) => {
    e.preventDefault();
    startTalking();
  },
  { passive: false }
);
talkButton.addEventListener(
  'touchend',
  (e) => {
    e.preventDefault();
    stopTalking();
  },
  { passive: false }
);

// =========================
// 2. Shaders de partículas
// =========================

// Vertex: movimiento tipo “campo” + respiración + boca hablando + tamaño fijo
const vertexShader = /* glsl */ `
precision highp float;

uniform float uPointSize;
uniform float uTime;
uniform float uGlobalAmp;
uniform float uClusterAmp;
uniform float uNoiseAmp;

// habla
uniform float uTalk;
uniform float uTalkAmpTop;
uniform float uTalkAmpBot;
uniform float uTalkFreq;
uniform float uLipDepthAmp;
uniform float uRestOpen;   // apertura mínima en reposo

// respiración
uniform float uBreathAmp;
uniform float uBreathFreq;

attribute vec3 aBasePosition;
attribute vec3 aRandom;
attribute float aClusterId;
attribute vec2 aUv;

// boca
attribute float aMouthWeight;
attribute float aMouthSide;

varying vec2 vUv;

// --- helpers de ruido simples --- //
float hash11(float p) {
  return fract(sin(p * 127.1) * 43758.5453123);
}

float hash21(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float simpleNoise(vec3 p, float t) {
  float n1 = hash21(p.xy + t);
  float n2 = hash21(p.yz - t * 0.5);
  return (n1 + n2) * 0.5; // 0..1
}

void main() {
  vUv = aUv;

  vec3 pos = aBasePosition;
  float t = uTime;

  // 1) ONDA GLOBAL SUAVE (como “campo” de la cara)
  float globalPhase = t * 0.5;
  float swayX = sin(globalPhase + aRandom.x * 6.2831);
  float swayY = cos(globalPhase * 0.8 + aRandom.y * 6.2831);

  vec3 globalOffset = vec3(
    swayX * 0.003,
    swayY * 0.002,
    0.0
  ) * uGlobalAmp;

  // 2) MOVIMIENTO POR CLUSTERS (manchas)
  float clusterPhase = hash11(aClusterId + 10.0) * 6.2831;
  float clusterAnim = sin(t * 0.8 + clusterPhase);

  vec3 clusterDir = normalize(vec3(
    hash11(aClusterId + 1.0) - 0.5,
    hash11(aClusterId + 2.0) - 0.5,
    hash11(aClusterId + 3.0) - 0.5
  ));

  vec3 clusterOffset = clusterDir * clusterAnim * 0.004 * uClusterAmp;

  // 3) MICRO-NOISE (ligero temblor elegante)
  float n = simpleNoise(aBasePosition * 1.5, t * 0.6);
  float micro = (n - 0.5); // -0.5..+0.5

  vec3 microDir = normalize(aRandom * 2.0 - 1.0);
  vec3 microOffset = microDir * micro * 0.002 * uNoiseAmp;

  // 3.5) RESPIRACIÓN SUAVE (más peso en zona baja)
  float breathPhase = sin(uTime * uBreathFreq) * 0.5 + 0.5; // 0..1
  float heightFactor = clamp(1.0 - (aBasePosition.y + 0.3) * 2.0, 0.0, 1.0);
  float breath = breathPhase * heightFactor * uBreathAmp;
  vec3 breathOffset = vec3(0.0, breath * 0.01, breath * 0.005);

  // 4) HABLA: labios arriba/abajo + un poco hacia dentro (Z-)
  float phase = sin(uTime * uTalkFreq);
  float talkOpen = max(phase, 0.0) * uTalk; // apertura por habla (0..1)

  // apertura total = rest + habla
  float totalOpen = uRestOpen + talkOpen;
  totalOpen = clamp(totalOpen, 0.0, 1.0);

  // +1 labio superior, -1 labio inferior
  float side = aMouthSide;

  // amplitud distinta arriba/abajo
  float lipAmp = mix(uTalkAmpBot, uTalkAmpTop, step(0.0, side));

  // factor total según peso de boca y apertura
  float mouthFactor = aMouthWeight * totalOpen;

  // desplazamiento vertical
  float verticalOffset = side * lipAmp * mouthFactor;

  // pequeño desplazamiento hacia dentro (Z-)
  float depthOffset = -uLipDepthAmp * mouthFactor;

  vec3 mouthOffset = vec3(
    0.0,
    verticalOffset,
    depthOffset
  );

  // POSICIÓN FINAL
  vec3 displaced = pos
    + globalOffset
    + clusterOffset
    + microOffset
    + breathOffset
    + mouthOffset;

  vec4 mvPosition = modelViewMatrix * vec4(displaced, 1.0);

  // Tamaño FIJO en pantalla (no depende de la distancia)
  gl_PointSize = uPointSize;

  gl_Position = projectionMatrix * mvPosition;
}
`;

// Fragment: disco suave + modulación por textura de color (zonas claras/oscuras)
const fragmentShader = /* glsl */ `
precision highp float;

uniform vec3 uColor;
uniform sampler2D uColorMap;
uniform float uUseMap; // 1.0 si hay textura, 0.0 si no

varying vec2 vUv;

void main() {
  // 1) círculo suave
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(p, p);
  if (r2 > 1.0) discard;

  float r = sqrt(r2);
  float circle = 1.0 - smoothstep(0.7, 1.0, r);

  // 2) leer color de la textura de piel (si existe)
  vec3 texColor = texture2D(uColorMap, vUv).rgb;

  // brillo 0..1
  float densityRaw = (texColor.r + texColor.g + texColor.b) / 3.0;
  // si no hay textura, usamos 1.0 (todo visible)
  float density = mix(1.0, densityRaw, uUseMap);

  // 3) mapear brillo → alpha (zonas oscuras casi desaparecen)
  float alphaMask = density;
  float alpha = circle * alphaMask;

  if (alpha < 0.02) discard;

  // 4) color final: base gris, ligeramente modulado por el brillo
  vec3 baseColor = uColor;
  vec3 finalColor = mix(baseColor * 0.6, baseColor, density);

  gl_FragColor = vec4(finalColor, alpha);
}
`;

// =========================
// 3. Generar puntos desde vértices (cara frontal) + UV
// =========================
function generateFaceParticlesFromVertices(srcGeometry) {
  const srcPos = srcGeometry.getAttribute('position');
  const srcUv  = srcGeometry.getAttribute('uv');

  const vertexCount = srcPos.count;

  const v = new THREE.Vector3();
  const uv = new THREE.Vector2();

  const posArray = [];
  const uvArray  = [];

  for (let i = 0; i < vertexCount; i++) {
    v.fromBufferAttribute(srcPos, i);

    // Corte frontal: solo puntos con Z >= 0 (ajusta si ves la cara al revés)
    if (v.z < 0.0) continue;

    posArray.push(v.x, v.y, v.z);

    if (srcUv) {
      uv.fromBufferAttribute(srcUv, i);
      uvArray.push(uv.x, uv.y);
    } else {
      // por si no hay UV, ponemos algo por defecto
      uvArray.push(0.0, 0.0);
    }
  }

  console.log('Vértices usados (cara frontal plano Z=0):', posArray.length / 3);

  const positions = new Float32Array(posArray);
  const uvs       = new Float32Array(uvArray);
  const count     = positions.length / 3;

  // Atributos extra para movimiento tipo Phantom
  const basePositions = new Float32Array(positions.length);
  basePositions.set(positions);

  const randoms    = new Float32Array(count * 3);
  const clusterIds = new Float32Array(count);

  // Boca
  const mouthWeights = new Float32Array(count);
  const mouthSides   = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    // random por punto
    randoms[i * 3 + 0] = Math.random();
    randoms[i * 3 + 1] = Math.random();
    randoms[i * 3 + 2] = Math.random();

    const x = positions[i * 3 + 0];
    const y = positions[i * 3 + 1];

    // clusterId simple a partir de X/Y (para mover “manchas” juntas)
    const cx = Math.floor((x + 0.4) * 10.0);
    const cy = Math.floor((y + 0.4) * 10.0);
    clusterIds[i] = cx + cy * 10.0;

    // ------- Cálculo de región de boca -------
    let dx = x - MOUTH_CENTER_X;
    let ax = Math.abs(dx);

    let weight = 0.0;
    let side   = 0.0;

    if (ax <= MOUTH_WIDTH) {
      let normX = dx / MOUTH_WIDTH;
      let curveY = MOUTH_CENTER_Y - MOUTH_CURVE * normX * normX;
      let dy = y - curveY;
      let ay = Math.abs(dy);

      if (ay <= MOUTH_HEIGHT) {
        let wx = 1.0 - ax / MOUTH_WIDTH;   // centro horizontal más peso
        let wy = 1.0 - ay / MOUTH_HEIGHT;  // cerca de la curva, más peso
        weight = wx * wy;

        if (weight < 0.0) weight = 0.0;
        if (weight > 1.0) weight = 1.0;

        if (dy > 0.0) {
          side = 1.0;     // labio superior
        } else if (dy < 0.0) {
          side = -1.0;    // labio inferior
        } else {
          side = 0.0;
        }
      }
    }

    mouthWeights[i] = weight;
    mouthSides[i]   = side;
  }

  const particlesGeo = new THREE.BufferGeometry();
  particlesGeo.setAttribute(
    'position',
    new THREE.BufferAttribute(positions, 3)
  );
  particlesGeo.setAttribute(
    'aUv',
    new THREE.BufferAttribute(uvs, 2)
  );
  particlesGeo.setAttribute(
    'aBasePosition',
    new THREE.BufferAttribute(basePositions, 3)
  );
  particlesGeo.setAttribute(
    'aRandom',
    new THREE.BufferAttribute(randoms, 3)
  );
  particlesGeo.setAttribute(
    'aClusterId',
    new THREE.BufferAttribute(clusterIds, 1)
  );
  particlesGeo.setAttribute(
    'aMouthWeight',
    new THREE.BufferAttribute(mouthWeights, 1)
  );
  particlesGeo.setAttribute(
    'aMouthSide',
    new THREE.BufferAttribute(mouthSides, 1)
  );

  return particlesGeo;
}

// Tamaño de punto fijo
const POINT_SIZE = 3.5 * window.devicePixelRatio;

// =========================
// 4. Cargar GLB, fusionar capas, crear partículas
// =========================
const loader = new GLTFLoader();

let particleMaterial = null;
let particlePoints = null; // <<< necesitamos referencia global para mover la cabeza

loader.load(
  './faceVolumen.glb',
  (gltf) => {
    console.log('GLB cargado correctamente');

    const meshes = [];
    gltf.scene.traverse((obj) => {
      if (obj.isMesh) meshes.push(obj);
    });

    console.log('Meshes encontrados:', meshes.map(m => m.name));
    if (!meshes.length) {
      console.error('No se encontraron mallas en el GLB');
      return;
    }

    // intentar recuperar la textura de color de la cara
    let colorMap = null;
    for (const m of meshes) {
      if (m.material && m.material.map) {
        colorMap = m.material.map;
        break;
      }
    }
    if (!colorMap) {
      console.warn('No se ha encontrado material.map (textura de color). Se usará densidad = 1 en todo.');
    }

    const geoms = [];
    meshes.forEach((m) => {
      const g = m.geometry.clone();
      m.updateWorldMatrix(true, false);
      g.applyMatrix4(m.matrixWorld);
      geoms.push(g);
    });

    const mergeFn =
      BufferGeometryUtils.mergeGeometries ||
      BufferGeometryUtils.mergeBufferGeometries;

    const mergedGeom = mergeFn(geoms, true);
    if (!mergedGeom) {
      console.error('Fallo al fusionar geometrías');
      return;
    }
    mergedGeom.computeVertexNormals();

    // centrar la malla fusionada
    mergedGeom.computeBoundingBox();
    const box = mergedGeom.boundingBox;
    const center = new THREE.Vector3();
    box.getCenter(center);
    mergedGeom.translate(-center.x, -center.y, -center.z);

    // Generar partículas a partir de los vértices (solo frontal) + UV
    const particlesGeo = generateFaceParticlesFromVertices(mergedGeom);

    particleMaterial = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      transparent: true,
      depthWrite: true,
      blending: THREE.NormalBlending,
      uniforms: {
        uPointSize:    { value: POINT_SIZE },
        uColor:        { value: new THREE.Color(0xdddddd) },
        uColorMap:     { value: colorMap },
        uUseMap:       { value: colorMap ? 1.0 : 0.0 },

        uTime:         { value: 0.0 },
        uGlobalAmp:    { value: 1.5 },
        uClusterAmp:   { value: 1.5 },
        uNoiseAmp:     { value: 1.6 },

        // habla
        uTalk:         { value: 0.0 },
        uTalkAmpTop:   { value: 0.012 }, // apertura labio superior
        uTalkAmpBot:   { value: 0.035 }, // apertura labio inferior
        uTalkFreq:     { value: 24.0 },  // velocidad "bla bla"
        uLipDepthAmp:  { value: 0.030 }, // cuánto entra hacia dentro

        // rest pose (apertura mínima constante)
        uRestOpen:     { value: 0.30 },

        // respiración
        uBreathAmp:    { value: 1.0 },  // cantidad de respiración
        uBreathFreq:   { value: 0.6 }   // velocidad respiración (lenta)
      }
    });

    particlePoints = new THREE.Points(particlesGeo, particleMaterial);
    particlePoints.frustumCulled = false;
    scene.add(particlePoints);

    controls.target.set(0, 0.15, 0);
    controls.update();
  },
  undefined,
  (err) => {
    console.error('Error cargando faceVolumen.glb', err);
  }
);

// =========================
// 5. Resize
// =========================
window.addEventListener('resize', () => {
  const w = window.innerWidth;
  const h = window.innerHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
});

// =========================
// 6. Loop
// =========================
function animate() {
  requestAnimationFrame(animate);

  const elapsed = clock.getElapsedTime();
  if (particleMaterial) {
    particleMaterial.uniforms.uTime.value = elapsed;
    particleMaterial.uniforms.uTalk.value = isTalking ? 1.0 : 0.0;
  }

  // movimiento global de cabeza/cuello (más vivo y menos lineal)
  if (particlePoints) {
    const t = elapsed;

    // combinamos varias senoidales para que no parezca péndulo perfecto
    const headYaw =
      Math.sin(t * 0.8) * 0.025 +   // movimiento principal
      Math.sin(t * 1.7) * 0.03;    // pequeña variación rápida

    const headPitch =
      Math.sin(t * 0.6 + 1.0) * 0.03 +
      Math.sin(t * 1.3) * 0.02;

    const headRoll =
      Math.sin(t * 0.45 + 2.0) * 0.03; // ligera inclinación lateral

    particlePoints.rotation.y = headYaw;   // izquierda-derecha
    particlePoints.rotation.x = headPitch; // arriba-abajo
    particlePoints.rotation.z = headRoll;  // cabeceo lateral

    // movimiento del cuerpo/cuello tipo “acomodo”
    particlePoints.position.y =
      0.01 * Math.sin(t * 0.9) +
      0.005 * Math.sin(t * 0.37);
  }

  controls.update();
  renderer.render(scene, camera);
}

animate();
