'use strict';
/**
 * Vérification des photos de profil : exactement UN visage humain, image nette.
 *
 * Fournisseurs (variable FACE_PROVIDER) :
 *  - "local"  (défaut) : modèle TinyFaceDetector + SSD MobileNet exécutés sur le serveur
 *                        (TensorFlow.js / WebAssembly). Gratuit, aucune donnée envoyée à un tiers.
 *  - "google"          : Google Cloud Vision API (FACE_DETECTION), clé GOOGLE_VISION_API_KEY.
 *  - "off"             : désactivé (toute photo part en validation manuelle).
 *
 * Retourne { ok, reason, faces, details } où reason ∈
 *   'no_face' | 'multiple_faces' | 'face_too_small' | 'blurry' | 'too_dark' | 'invalid_image' | 'provider_error' | null
 */
const path = require('path');
const sharp = require('sharp');

const MIN_FACE_RATIO = 0.12;   // le visage doit occuper au moins 12 % de la largeur de l'image
const MIN_SHARPNESS = 4;       // écart-type du laplacien en dessous = image floue
const MIN_BRIGHTNESS = 25;     // luminance moyenne (0-255) en dessous = trop sombre
const MIN_SCORE = 0.5;

let faceapi = null;
let tf = null;
let loading = null;

async function loadLocal() {
  if (faceapi) return;
  if (!loading) {
    loading = (async () => {
      faceapi = require('@vladmandic/face-api/dist/face-api.node-wasm.js');
      tf = faceapi.tf;
      const wasmDir = path.join(path.dirname(require.resolve('@tensorflow/tfjs-backend-wasm')), '/');
      try {
        tf.setWasmPaths(wasmDir);
        await tf.setBackend('wasm');
      } catch (e) {
        await tf.setBackend('cpu');
      }
      await tf.ready();
      const modelDir = path.join(path.dirname(require.resolve('@vladmandic/face-api/package.json')), 'model');
      await faceapi.nets.ssdMobilenetv1.loadFromDisk(modelDir);
    })();
  }
  await loading;
}

/** Netteté (écart-type du laplacien) et luminosité moyenne, calculées sur une version 256 px en niveaux de gris. */
async function imageQuality(buffer) {
  const { data, info } = await sharp(buffer).rotate().resize(256, 256, { fit: 'inside' })
    .greyscale().raw().toBuffer({ resolveWithObject: true });
  const w = info.width; const h = info.height; const ch = info.channels;
  const px = (x, y) => data[(y * w + x) * ch];
  let sum = 0;
  for (let i = 0; i < w * h; i++) sum += data[i * ch];
  let n = 0; let m = 0; let m2 = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const l = px(x - 1, y) + px(x + 1, y) + px(x, y - 1) + px(x, y + 1) - 4 * px(x, y);
      n++; const d = l - m; m += d / n; m2 += d * (l - m);
    }
  }
  return { brightness: sum / (w * h), sharpness: Math.sqrt(m2 / Math.max(1, n)) };
}

async function detectLocal(buffer) {
  await loadLocal();
  const { data, info } = await sharp(buffer).rotate()
    .resize(512, 512, { fit: 'inside', withoutEnlargement: true })
    .removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const tensor = tf.tensor3d(new Uint8Array(data), [info.height, info.width, 3], 'int32');
  try {
    const dets = await faceapi.detectAllFaces(tensor, new faceapi.SsdMobilenetv1Options({ minConfidence: MIN_SCORE }));
    return {
      width: info.width,
      faces: dets.map((d) => ({ score: d.score, width: d.box.width, height: d.box.height, x: d.box.x, y: d.box.y })),
    };
  } finally {
    tensor.dispose();
  }
}

async function detectGoogle(buffer) {
  const key = process.env.GOOGLE_VISION_API_KEY;
  if (!key) throw new Error('GOOGLE_VISION_API_KEY manquante');
  const small = await sharp(buffer).rotate().resize(640, 640, { fit: 'inside', withoutEnlargement: true }).jpeg().toBuffer();
  const meta = await sharp(small).metadata();
  const res = await fetch(`https://vision.googleapis.com/v1/images:annotate?key=${encodeURIComponent(key)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ requests: [{ image: { content: small.toString('base64') }, features: [{ type: 'FACE_DETECTION', maxResults: 5 }] }] }),
  });
  if (!res.ok) throw new Error(`Google Vision HTTP ${res.status}`);
  const json = await res.json();
  const anns = (json.responses && json.responses[0] && json.responses[0].faceAnnotations) || [];
  return {
    width: meta.width,
    faces: anns.filter((a) => a.detectionConfidence >= MIN_SCORE).map((a) => {
      const v = a.fdBoundingPoly.vertices;
      const xs = v.map((p) => p.x || 0); const ys = v.map((p) => p.y || 0);
      return { score: a.detectionConfidence, width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) };
    }),
  };
}

async function checkProfilePhoto(buffer) {
  const provider = (process.env.FACE_PROVIDER || 'local').toLowerCase();
  let meta;
  try {
    meta = await sharp(buffer).metadata();
    if (!['jpeg', 'png', 'webp'].includes(meta.format)) return { ok: false, reason: 'invalid_image', faces: 0 };
    if ((meta.width || 0) < 200 || (meta.height || 0) < 200) return { ok: false, reason: 'invalid_image', faces: 0 };
  } catch (e) {
    return { ok: false, reason: 'invalid_image', faces: 0 };
  }
  if (provider === 'off') return { ok: false, reason: 'provider_error', faces: 0, details: 'disabled' };

  const q = await imageQuality(buffer);
  if (q.brightness < MIN_BRIGHTNESS) return { ok: false, reason: 'too_dark', faces: 0, details: q };
  if (q.sharpness < MIN_SHARPNESS) return { ok: false, reason: 'blurry', faces: 0, details: q };

  let result;
  try {
    result = provider === 'google' ? await detectGoogle(buffer) : await detectLocal(buffer);
  } catch (e) {
    console.error('[faceDetection]', e.message);
    return { ok: false, reason: 'provider_error', faces: 0, details: e.message };
  }
  const n = result.faces.length;
  if (n === 0) return { ok: false, reason: 'no_face', faces: 0, details: q };
  if (n > 1) return { ok: false, reason: 'multiple_faces', faces: n, details: q };
  const f = result.faces[0];
  if (f.width / result.width < MIN_FACE_RATIO) return { ok: false, reason: 'face_too_small', faces: 1, details: { ...q, ratio: f.width / result.width } };
  return { ok: true, reason: null, faces: 1, details: { ...q, score: f.score, ratio: f.width / result.width } };
}

/** Pré-chargement du modèle au démarrage pour que la 1re vérification soit rapide. */
function warmUp() {
  if ((process.env.FACE_PROVIDER || 'local').toLowerCase() === 'local') {
    loadLocal().then(() => console.log('[faceDetection] modèle local chargé')).catch((e) => console.error('[faceDetection] chargement échoué', e.message));
  }
}

module.exports = { checkProfilePhoto, warmUp };
