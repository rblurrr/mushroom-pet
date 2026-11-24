const VISION_URL = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.17";
const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.17/wasm";
const OBJECT_MODEL = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/1/efficientdet_lite0.task";
const GESTURE_MODEL = "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task";

export function watchCamera(video, onEvent, onMode) {
  let stopped = false;
  let objects = null;
  let gestures = null;
  let lastText = "";
  let lastSent = 0;
  const canvas = document.createElement("canvas");
  canvas.width = 48;
  canvas.height = 36;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  let previous = null;
  let flips = 0;
  let lastSide = 0;

  onMode("On-device motion. MediaPipe is loading.");
  loadMediaPipe(video).then((models) => {
    if (stopped || !models) {
      if (!stopped) onMode("On-device motion. Frames stay in this browser.");
      return;
    }
    objects = models.objects;
    gestures = models.gestures;
    onMode("On-device MediaPipe. Frames stay in this browser.");
  }).catch(() => {
    if (!stopped) onMode("On-device motion. Frames stay in this browser.");
  });

  const timer = setInterval(() => {
    if (stopped || video.readyState < 2) return;
    const text = objects ? readModels(video, objects, gestures) : readMotion();
    if (!text || text === lastText) return;
    const now = Date.now();
    if (now - lastSent < 6000 && !/wave/.test(text)) return;
    lastText = text;
    lastSent = now;
    onEvent(text);
  }, 700);

  function readMotion() {
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const frame = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    if (!previous) {
      previous = frame;
      return "";
    }
    let changed = 0;
    let cx = 0;
    for (let i = 0; i < frame.length; i += 16) {
      const delta = Math.abs(frame[i] - previous[i]) + Math.abs(frame[i + 1] - previous[i + 1]) + Math.abs(frame[i + 2] - previous[i + 2]);
      if (delta > 40) {
        changed += 1;
        cx += (i / 4) % canvas.width;
      }
    }
    previous = frame;
    if (changed < 12) {
      flips = 0;
      return "";
    }
    const center = cx / changed;
    const side = center < canvas.width / 2 ? -1 : 1;
    if (lastSide && side !== lastSide) flips += 1;
    lastSide = side;
    if (flips >= 3) {
      flips = 0;
      return "motion that looks like a wave";
    }
    return "something moved";
  }

  return () => {
    stopped = true;
    clearInterval(timer);
    objects?.close?.();
    gestures?.close?.();
  };
}

async function loadMediaPipe() {
  const module = await import(VISION_URL);
  const files = await module.FilesetResolver.forVisionTasks(WASM);
  const objects = await module.ObjectDetector.createFromOptions(files, {
    baseOptions: { modelAssetPath: OBJECT_MODEL },
    runningMode: "VIDEO",
    scoreThreshold: 0.45,
  });
  const gestures = await module.GestureRecognizer.createFromOptions(files, {
    baseOptions: { modelAssetPath: GESTURE_MODEL },
    runningMode: "VIDEO",
    numHands: 1,
  });
  return { objects, gestures };
}

function readModels(video, objects, gestures) {
  const now = performance.now();
  const found = objects.detectForVideo(video, now);
  const names = [];
  for (const hit of found.detections || []) {
    const name = hit.categories?.[0]?.categoryName;
    if (name && !names.includes(name)) names.push(name);
  }
  let wave = false;
  let hand = false;
  if (gestures) {
    const hands = gestures.recognizeForVideo(video, now);
    const gesture = hands.gestures?.[0]?.[0];
    if (gesture && gesture.score > 0.5) {
      hand = true;
      if (gesture.categoryName === "Open_Palm" || gesture.categoryName === "Victory") wave = true;
    }
    if ((hands.landmarks || []).length) hand = true;
  }
  if (wave) return "a person waved";
  if (names.includes("person")) return hand ? "a person, with a hand up" : "a person";
  if (hand) return "a hand";
  const thing = names.find((name) => name !== "person");
  if (thing) return `a ${thing.replaceAll("_", " ")}`;
  return "";
}
