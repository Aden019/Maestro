const BONES = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [17, 18], [18, 19], [19, 20],
  [0, 17],
];
const FINGER_OF_POINT = (index) => (index === 0 ? -1 : Math.min(4, Math.floor((index - 1) / 4)));
const TIPS = new Set([4, 8, 12, 16, 20]);
const FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"];

const ROWS = [
  { gesture: "fist", label: "Closed fist", fingers: [0, 0, 0, 0, 0], wake: true },
  { gesture: "sleep", sleep: true },
  { gesture: "victory", label: "Two fingers", fingers: [0, 1, 1, 0, 0] },
  { gesture: "three", label: "Three fingers", fingers: [0, 1, 1, 1, 0] },
  { gesture: "shaka", label: "Thumb & little finger", fingers: [1, 0, 0, 0, 1] },
  { gesture: "point", label: "Point", fingers: [0, 1, 0, 0, 0], fixed: "Move the cursor" },
  { gesture: "pinch", label: "Pinch while pointing", fingers: [1, 1, 0, 0, 0], fixed: "Click or drag" },
  { gesture: "open", label: "Open hand, up or down", fingers: [1, 1, 1, 1, 1], fixed: "Scroll" },
];

const SLEEP_CHOICES = {
  thumbs_up: { label: "Thumbs up", fingers: [1, 0, 0, 0, 0] },
  rock: { label: "Rock sign", fingers: [0, 1, 0, 0, 1] },
};

const BRASS = "#dcaa4b";
const CREAM = "240, 231, 212";
const SERIF = 'ui-serif, "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif';
const MONO = 'ui-monospace, "SF Mono", Menlo, monospace';
const ROLL_SECONDS = 14;
const ROLL_GUTTER = 62;
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

const elements = {
  body: document.body,
  demoTag: document.getElementById("demo-tag"),
  baton: document.getElementById("baton"),
  batonLabel: document.getElementById("baton-label"),
  viewfinder: document.getElementById("viewfinder"),
  overlay: document.getElementById("overlay"),
  fps: document.getElementById("fps"),
  notice: document.getElementById("notice"),
  noticeTitle: document.getElementById("notice-title"),
  noticeText: document.getElementById("notice-text"),
  retry: document.getElementById("retry"),
  access: document.getElementById("access"),
  accessButton: document.getElementById("access-button"),
  cue: document.getElementById("cue"),
  rows: document.getElementById("score-rows"),
  apps: document.getElementById("apps"),
  roll: document.getElementById("roll"),
  programme: document.getElementById("programme"),
};

let state = null;
let shownHand = null;
let lastFiredId = null;
let lastLogId = null;
let bloom = null;
const rowViews = new Map();
const samples = [];
const marks = [];

const NOTICES = {
  starting: ["Finding your camera", "This should only take a moment."],
  denied: [
    "Maestro can’t see you yet",
    "Open System Settings, then Privacy & Security, then Camera, and allow the app you started Maestro from. Restart Maestro after changing this.",
  ],
  missing: ["The camera stopped", "It may be in use by another app, such as a video call. Close that app and try again."],
  error: ["Hand tracking couldn’t start", "Check that models/hand_landmarker.task is still in the Maestro folder, then restart."],
};

function post(path, body) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function sizeCanvas(canvas) {
  const scale = devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  const pixelWidth = Math.round(width * scale);
  const pixelHeight = Math.round(height * scale);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  const context = canvas.getContext("2d");
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, width, height);
  return { context, width, height };
}

// The score

// Draws a gesture as a simple hand shape: a palm, raised fingers, and stubs for folded ones.
function makeGlyph(pose, fingers) {
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  svg.setAttribute("class", "glyph");
  svg.setAttribute("viewBox", "0.12 0.16 0.72 0.76");
  svg.setAttribute("aria-hidden", "true");

  const palm = document.createElementNS(namespace, "polygon");
  palm.setAttribute("points", [1, 5, 9, 13, 17, 0].map((i) => pose[i].join(",")).join(" "));
  svg.append(palm);

  const FINGER_POINTS = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16], [17, 18, 19, 20]];
  FINGER_POINTS.forEach((points, finger) => {
    const shown = fingers[finger] ? points : points.slice(0, 2);
    const line = document.createElementNS(namespace, "polyline");
    line.setAttribute("points", shown.map((i) => pose[i].join(",")).join(" "));
    svg.append(line);
  });
  return svg;
}

function startEditing(gesture, button) {
  const input = document.createElement("input");
  input.className = "app-name";
  input.value = button.textContent;
  input.setAttribute("list", "apps");
  input.setAttribute("aria-label", "App to open");

  let finished = false;
  const finish = async (save) => {
    if (finished) return;
    finished = true;
    const app = input.value.trim();
    if (save && app && app !== button.textContent) {
      const response = await post("/api/binding", { gesture, app });
      if (!response.ok) elements.cue.textContent = `“${app}” isn’t an app on this Mac.`;
    }
    input.replaceWith(button);
  };

  input.addEventListener("blur", () => finish(true));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") finish(true);
    if (event.key === "Escape") finish(false);
  });
  button.replaceWith(input);
  input.focus();
  input.select();
}

function buildSleepRow(poses) {
  const row = document.createElement("li");
  row.className = "row app-row";

  const text = document.createElement("div");
  const choice = document.createElement("select");
  choice.className = "sleep-choice";
  choice.setAttribute("aria-label", "Gesture for sleep");
  for (const [gesture, { label }] of Object.entries(SLEEP_CHOICES)) choice.append(new Option(label, gesture));
  choice.addEventListener("change", () => post("/api/sleep-gesture", { gesture: choice.value }));

  const value = document.createElement("span");
  value.className = "wake-name";
  value.textContent = "Sleep";
  text.append(choice, value);

  const fill = document.createElement("i");
  fill.className = "fill";
  row.append(makeGlyph(poses.thumbs_up, SLEEP_CHOICES.thumbs_up.fingers), text, fill);
  elements.rows.append(row);
  rowViews.set("sleep", { row, value, fill, sleep: true, choice, poses, shownGesture: "thumbs_up" });
}

function renderSleepRow(view) {
  const gesture = state.sleepGesture;
  if (document.activeElement !== view.choice) view.choice.value = gesture;
  if (view.shownGesture !== gesture) {
    view.row.querySelector(".glyph").replaceWith(makeGlyph(view.poses[gesture], SLEEP_CHOICES[gesture].fingers));
    view.shownGesture = gesture;
  }
}

function buildScore(poses) {
  for (const { gesture, label, fingers, wake, fixed, sleep } of ROWS) {
    if (sleep) {
      buildSleepRow(poses);
      continue;
    }
    const row = document.createElement("li");
    row.className = wake ? "row" : "row app-row";
    row.append(makeGlyph(poses[gesture], fingers));

    const text = document.createElement("div");
    const name = document.createElement("span");
    name.className = "gesture-name";
    name.textContent = label;
    text.append(name);

    let value;
    if (wake || fixed) {
      value = document.createElement("span");
      value.className = "wake-name";
      value.textContent = fixed ?? "Wake";
    } else {
      value = document.createElement("button");
      value.type = "button";
      value.className = "app-name";
      value.setAttribute("aria-label", `Change the app for ${label}`);
      value.addEventListener("click", () => startEditing(gesture, value));
    }
    text.append(value);

    const fill = document.createElement("i");
    fill.className = "fill";
    row.append(text, fill);
    elements.rows.append(row);
    rowViews.set(gesture, { row, value, fill, wake, fixed });
  }
}

function isRowActive(gesture, view) {
  const { mode, pressed } = state.pointer;
  if (view.fixed) {
    if (gesture === "point") return mode === "cursor" && !pressed;
    if (gesture === "pinch") return pressed;
    return mode === "scroll";
  }
  return state.gesture === gesture && Boolean(state.target);
}

function renderScore() {
  for (const [name, view] of rowViews) {
    const gesture = view.sleep ? state.sleepGesture : name;
    const holding = state.gesture === gesture && state.progress > 0;
    view.row.classList.toggle("active", isRowActive(gesture, view));
    view.fill.style.setProperty("--progress", holding ? state.progress : 0);
    if (view.sleep) renderSleepRow(view);
    if (view.fixed || view.sleep || view.wake) continue;
    const text = state.bindings[gesture];
    if (view.value.textContent !== text) view.value.textContent = text;
  }
  elements.access.hidden = state.pointer.permission;
}

// Text around the picture

function cueText() {
  if (state.camera !== "ok") return "";
  if (state.progress > 0 && state.target) {
    return state.gesture === "fist" ? `Hold… ${state.target.toLowerCase()}` : `Hold… ${state.target}`;
  }
  if (!state.hand) return "Raise a hand into the frame.";
  if (!state.listening) return "Close your fist and hold it to begin.";
  if (state.pointer.pressed) return "Holding the click. Open your pinch to let go.";
  if (state.pointer.mode === "cursor") return "Steering the cursor. Pinch to click.";
  if (state.pointer.mode === "scroll") return "Move your open hand up or down to scroll.";
  if (state.gesture === "open") return "Ready. Make a gesture from the score.";
  return "Listening.";
}

function renderProgramme() {
  const newest = state.log[0]?.id ?? null;
  if (newest === lastLogId && lastLogId !== null) return;
  if (newest === null) {
    if (!elements.programme.firstChild) {
      const empty = document.createElement("li");
      empty.className = "placeholder";
      empty.textContent = "Nothing played yet.";
      elements.programme.append(empty);
    }
    return;
  }
  lastLogId = newest;
  elements.programme.replaceChildren(
    ...state.log.slice(0, 5).map((entry) => {
      const item = document.createElement("li");
      item.className = entry.kind;
      const time = document.createElement("time");
      time.textContent = entry.time;
      const text = document.createElement("span");
      text.textContent = entry.text;
      item.append(time, text);
      return item;
    }),
  );
}

function renderChrome() {
  elements.body.dataset.listening = state.listening;
  elements.baton.setAttribute("aria-pressed", state.listening);
  elements.batonLabel.textContent = state.listening ? "Listening" : "Asleep";
  elements.demoTag.hidden = !state.demo;
  elements.fps.textContent = state.camera === "ok" ? `${state.fps} fps` : "— fps";
  elements.viewfinder.parentElement.style.setProperty("--aspect", state.aspect);

  const notice = NOTICES[state.camera];
  elements.notice.hidden = !notice;
  if (notice) {
    elements.noticeTitle.textContent = notice[0];
    elements.noticeText.textContent = notice[1];
    elements.retry.hidden = state.camera === "starting" || state.camera === "error";
  }

  const cue = cueText();
  if (elements.cue.textContent !== cue) elements.cue.textContent = cue;
}

function handleFired() {
  const fired = state.fired;
  if (!fired || fired.id === lastFiredId) return;
  const isFirstMessage = lastFiredId === null && samples.length <= 1;
  lastFiredId = fired.id;
  if (isFirstMessage) return;

  const text = fired.kind === "open" ? fired.app : fired.kind === "listen" ? "Listening" : "Asleep";
  const palm = shownHand ? palmOf(shownHand) : { x: 0.5, y: 0.5, size: 0.1 };
  bloom = { text, x: palm.x, y: palm.y, size: palm.size, startedAt: performance.now() };
  marks.push({ t: performance.now(), text });
}

// The picture overlay

function palmOf(hand) {
  const x = (hand[0][0] + hand[5][0] + hand[17][0]) / 3;
  const y = (hand[0][1] + hand[5][1] + hand[17][1]) / 3;
  const size = Math.hypot(hand[0][0] - hand[9][0], hand[0][1] - hand[9][1]);
  return { x, y, size };
}

function smoothHand() {
  if (!state?.hand) {
    shownHand = null;
    return;
  }
  if (!shownHand) {
    shownHand = state.hand.map((point) => [...point]);
    return;
  }
  // Follow quickly, so it feels attached to the hand while hiding tracking jitter.
  shownHand = shownHand.map((point, i) => [
    point[0] + (state.hand[i][0] - point[0]) * 0.5,
    point[1] + (state.hand[i][1] - point[1]) * 0.5,
  ]);
}

function drawHand(context, width, height) {
  const at = (point) => [point[0] * width, point[1] * height];
  const isLit = (index) => {
    const finger = FINGER_OF_POINT(index);
    return finger >= 0 && state.fingers[finger];
  };

  context.lineCap = "round";
  for (const [from, to] of BONES) {
    const lit = isLit(to) && (from === 0 || FINGER_OF_POINT(from) === FINGER_OF_POINT(to));
    context.strokeStyle = lit ? BRASS : `rgba(${CREAM}, 0.48)`;
    context.lineWidth = lit ? 2.25 : 1.25;
    context.beginPath();
    context.moveTo(...at(shownHand[from]));
    context.lineTo(...at(shownHand[to]));
    context.stroke();
  }

  shownHand.forEach((point, index) => {
    const [x, y] = at(point);
    const tip = TIPS.has(index);
    context.fillStyle = tip && isLit(index) ? BRASS : `rgb(${CREAM})`;
    context.beginPath();
    context.arc(x, y, tip ? 4 : 2, 0, Math.PI * 2);
    context.fill();
  });
}

function drawHoldRing(context, width, height) {
  if (!shownHand || !state.target || state.progress <= 0) return;
  const palm = palmOf(shownHand);
  const x = palm.x * width;
  const y = palm.y * height;
  const radius = Math.max(44, palm.size * height * 0.8);
  const ticks = 48;

  // Each tick lights up in turn as the gesture is held, like a dial turning.
  for (let i = 0; i < ticks; i += 1) {
    const angle = -Math.PI / 2 + (i / ticks) * Math.PI * 2;
    const lit = i / ticks < state.progress;
    const inner = radius + (lit ? 0 : 3);
    const outer = radius + (lit ? 13 : 9);
    context.strokeStyle = lit ? BRASS : `rgba(${CREAM}, 0.32)`;
    context.lineWidth = lit ? 2 : 1;
    context.beginPath();
    context.moveTo(x + Math.cos(angle) * inner, y + Math.sin(angle) * inner);
    context.lineTo(x + Math.cos(angle) * outer, y + Math.sin(angle) * outer);
    context.stroke();
  }

  context.font = `italic 500 22px ${SERIF}`;
  context.textAlign = "center";
  context.textBaseline = "top";
  context.fillStyle = `rgb(${CREAM})`;
  context.shadowColor = "rgba(0, 0, 0, 0.75)";
  context.shadowBlur = 8;
  context.fillText(state.target, x, Math.min(y + radius + 22, height - 34));
  context.shadowBlur = 0;
}

function drawCursorGuide(context, width, height) {
  if (state.pointer.mode !== "cursor" || !shownHand) return;
  const { left, right, top, bottom } = state.pointer.region;

  // The part of the view that stands for the whole screen.
  context.strokeStyle = `rgba(${CREAM}, 0.28)`;
  context.lineWidth = 1;
  context.setLineDash([3, 5]);
  context.strokeRect(left * width, top * height, (right - left) * width, (bottom - top) * height);
  context.setLineDash([]);

  const x = shownHand[5][0] * width;
  const y = shownHand[5][1] * height;
  const pressed = state.pointer.pressed;
  context.strokeStyle = BRASS;
  context.lineWidth = 1.5;
  context.beginPath();
  context.moveTo(x - 18, y);
  context.lineTo(x - 8, y);
  context.moveTo(x + 8, y);
  context.lineTo(x + 18, y);
  context.moveTo(x, y - 18);
  context.lineTo(x, y - 8);
  context.moveTo(x, y + 8);
  context.lineTo(x, y + 18);
  context.stroke();
  context.beginPath();
  context.arc(x, y, pressed ? 8 : 5, 0, Math.PI * 2);
  if (pressed) {
    context.fillStyle = BRASS;
    context.fill();
  } else {
    context.stroke();
  }
}

function drawBloom(context, width, height) {
  if (!bloom) return;
  const age = (performance.now() - bloom.startedAt) / 1100;
  if (age >= 1) {
    bloom = null;
    return;
  }

  const fade = 1 - age;
  if (!reducedMotion) {
    const x = bloom.x * width;
    const y = bloom.y * height;
    const radius = Math.max(44, bloom.size * height * 0.95) + 180 * (1 - fade ** 3);
    context.strokeStyle = `rgba(220, 170, 75, ${fade * 0.9})`;
    context.lineWidth = 1 + fade * 2;
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.stroke();
  }

  context.font = `italic 500 ${Math.round(Math.min(68, width * 0.075))}px ${SERIF}`;
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillStyle = `rgba(${CREAM}, ${Math.min(1, fade * 1.8)})`;
  context.shadowColor = "rgba(0, 0, 0, 0.8)";
  context.shadowBlur = 18;
  context.fillText(bloom.text, width / 2, height / 2);
  context.shadowBlur = 0;
}

function drawOverlay() {
  const { context, width, height } = sizeCanvas(elements.overlay);
  if (!state) return;
  smoothHand();
  if (shownHand) {
    drawHand(context, width, height);
    drawCursorGuide(context, width, height);
    drawHoldRing(context, width, height);
  }
  drawBloom(context, width, height);
}

// The finger roll

function drawRoll() {
  const { context, width, height } = sizeCanvas(elements.roll);
  const now = performance.now();
  const trackWidth = width - ROLL_GUTTER;
  const rowHeight = height / FINGER_NAMES.length;
  const xOf = (t) => ROLL_GUTTER + trackWidth - ((now - t) / (ROLL_SECONDS * 1000)) * trackWidth;

  while (samples.length > 1 && samples[1].t < now - ROLL_SECONDS * 1000) samples.shift();
  while (marks.length && marks[0].t < now - ROLL_SECONDS * 1000) marks.shift();

  context.textBaseline = "middle";
  context.textAlign = "left";
  FINGER_NAMES.forEach((name, finger) => {
    const y = rowHeight * (finger + 0.5);
    context.font = `11px ${MONO}`;
    context.fillStyle = "#a0947f";
    context.fillText(name, 0, y);

    context.strokeStyle = "#2e2820";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(ROLL_GUTTER, Math.round(y) + 0.5);
    context.lineTo(width, Math.round(y) + 0.5);
    context.stroke();

    // Joins neighbouring samples into solid bars while the finger stays raised.
    context.fillStyle = BRASS;
    const barHeight = Math.min(9, rowHeight * 0.45);
    let barStart = null;
    for (let i = 0; i < samples.length; i += 1) {
      const raised = samples[i].fingers[finger];
      if (raised && barStart === null) barStart = samples[i].t;
      const isLast = i === samples.length - 1;
      if (barStart !== null && (!raised || isLast)) {
        const left = Math.max(ROLL_GUTTER, xOf(barStart));
        const right = xOf(isLast && raised ? now : samples[i].t);
        if (right > left) context.fillRect(left, y - barHeight / 2, right - left, barHeight);
        barStart = null;
      }
    }
  });

  context.textBaseline = "top";
  for (const mark of marks) {
    const x = xOf(mark.t);
    if (x < ROLL_GUTTER) continue;
    context.strokeStyle = `rgba(${CREAM}, 0.75)`;
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(Math.round(x) + 0.5, 0);
    context.lineTo(Math.round(x) + 0.5, height);
    context.stroke();
    context.font = `italic 14px ${SERIF}`;
    context.textAlign = "right";
    context.fillStyle = `rgb(${CREAM})`;
    context.shadowColor = "#14110e";
    context.shadowBlur = 5;
    context.fillText(mark.text, x - 6, 1);
    context.shadowBlur = 0;
  }
}

function animate() {
  drawOverlay();
  drawRoll();
  requestAnimationFrame(animate);
}

// Wiring

elements.baton.addEventListener("click", () => {
  if (state) post("/api/listening", { listening: !state.listening });
});

elements.retry.addEventListener("click", () => post("/api/retry-camera", {}));
elements.accessButton.addEventListener("click", () => post("/api/cursor-permission", {}));

const setup = await fetch("/api/setup").then((response) => response.json());
buildScore(setup.poses);
elements.apps.replaceChildren(...setup.apps.map((app) => new Option(app, app)));

new EventSource("/events").addEventListener("message", (event) => {
  state = JSON.parse(event.data);
  samples.push({ t: performance.now(), fingers: state.fingers });
  handleFired();
  renderChrome();
  renderScore();
  renderProgramme();
});

animate();
