/* Chess Arena — frontend controller
 * Talks to the Flask API at /api/game/*
 * Board index: 0 = a8 … 63 = h1  (matches engine.py layout)
 */

"use strict";

const API = "/api/game";

// ── Piece glyphs ────────────────────────────────────────────────────────────
// Use the SOLID glyphs for both colours; the white/black look comes from the
// fill colour + outline in CSS. (The hollow glyphs ♔♕… render white-on-light as
// near-invisible, which is why white pieces looked transparent.)
const GLYPH = {
  wK: "♚", wQ: "♛", wR: "♜", wB: "♝", wN: "♞", wP: "♟",
  bK: "♚", bQ: "♛", bR: "♜", bB: "♝", bN: "♞", bP: "♟",
};

// ── State ───────────────────────────────────────────────────────────────────
let state = null;       // last API response
let flipped = false;    // board orientation (true = black at bottom)
let selected = null;    // currently selected square index
let legalTargets = [];  // legal destination square indices for selected piece
let pendingPromo = null;// { from, to } waiting for promotion pick

// ── DOM refs ─────────────────────────────────────────────────────────────────
const banterWrap   = document.getElementById("banter-wrap");
const banterText   = document.getElementById("banter-text");
const boardEl      = document.getElementById("board");
const moveListEl   = document.getElementById("move-list");
const statusEl     = document.getElementById("status-text");
const evalFill     = document.getElementById("eval-fill");
const evalLabelW   = document.getElementById("eval-label-w");
const evalLabelB   = document.getElementById("eval-label-b");
const promoDialog  = document.getElementById("promo-dialog");
const promoChoices = document.getElementById("promo-choices");
const overlay      = document.getElementById("gameover-overlay");
const overlayTitle = document.getElementById("overlay-title");
const overlaySub   = document.getElementById("overlay-sub");
const overlayIcon  = document.getElementById("overlay-icon");
const nameTop      = document.getElementById("name-top");
const nameBottom   = document.getElementById("name-bottom");
const materialTop  = document.getElementById("material-top");
const materialBottom = document.getElementById("material-bottom");

// ── Utility ──────────────────────────────────────────────────────────────────
const FILES = "abcdefgh";

function sqIndex(name) {
  return FILES.indexOf(name[0]) + (8 - parseInt(name[1])) * 8;
}
function sqName(i) {
  return FILES[i & 7] + String(8 - (i >> 3));
}

// visual row/col given flipped flag
function visualRC(idx) {
  const r = idx >> 3, c = idx & 7;
  return flipped ? { r: 7 - r, c: 7 - c } : { r, c };
}

// ── Board rendering ──────────────────────────────────────────────────────────
function buildBoard() {
  boardEl.innerHTML = "";
  const squares = [];

  for (let vr = 0; vr < 8; vr++) {
    for (let vc = 0; vc < 8; vc++) {
      const idx = flipped ? (7 - vr) * 8 + (7 - vc) : vr * 8 + vc;
      const sq = document.createElement("div");
      sq.className = "sq " + ((vr + vc) % 2 === 0 ? "light" : "dark");
      sq.dataset.idx = idx;

      // rank label (left edge)
      if (vc === 0) {
        const rank = document.createElement("span");
        rank.className = "coord-rank";
        rank.textContent = flipped ? String(vr + 1) : String(8 - vr);
        sq.appendChild(rank);
      }
      // file label (bottom edge)
      if (vr === 7) {
        const file = document.createElement("span");
        file.className = "coord-file";
        file.textContent = flipped ? FILES[7 - vc] : FILES[vc];
        sq.appendChild(file);
      }

      sq.addEventListener("click", onSquareClick);
      boardEl.appendChild(sq);
      squares.push(sq);
    }
  }
  return squares;
}

function renderBoard(gs) {
  // Rebuild if needed (flip changed)
  if (boardEl.children.length !== 64) buildBoard();

  const sqEls = [...boardEl.querySelectorAll(".sq")];
  const lastFrom = gs.lastMove ? sqIndex(gs.lastMove.from) : -1;
  const lastTo   = gs.lastMove ? sqIndex(gs.lastMove.to)   : -1;
  const checkKing = gs.inCheck ? sqIndex(gs.kingSquare) : -1;

  sqEls.forEach(sq => {
    const idx = parseInt(sq.dataset.idx);
    const isDark = sq.classList.contains("dark");

    // reset classes (keep light/dark)
    sq.className = "sq " + (isDark ? "dark" : "light");

    // last move highlight
    if (idx === lastFrom || idx === lastTo) sq.classList.add("last-move");

    // selected + legal targets
    if (idx === selected) sq.classList.add("selected");
    if (legalTargets.includes(idx)) {
      sq.classList.add("hint");
      if (gs.board[idx]) sq.classList.add("capture");
    }

    // king in check
    if (idx === checkKing) sq.classList.add("in-check");

    // piece
    let piece = sq.querySelector(".piece");
    const p = gs.board[idx];
    if (p) {
      if (!piece) {
        piece = document.createElement("span");
        piece.className = "piece";
        sq.appendChild(piece);
      }
      piece.textContent = GLYPH[p];
      piece.className = "piece " + (p[0] === "w" ? "white" : "black");
    } else {
      if (piece) piece.remove();
    }
  });
}

// ── Move list ─────────────────────────────────────────────────────────────────
const SOURCE_BADGE = {
  book:   ["book",   "Book"],
  clone:  ["clone",  "Clone"],
  engine: ["engine", "Engine"],
  style:  ["style",  "Style"],
};

function renderMoveList(history) {
  moveListEl.innerHTML = "";
  history.forEach((entry, i) => {
    if (i % 2 === 0) {
      const num = document.createElement("span");
      num.className = "move-num";
      num.textContent = String(Math.floor(i / 2) + 1) + ".";
      moveListEl.appendChild(num);
    }
    const cell = document.createElement("span");
    cell.className = "move-san";
    cell.textContent = entry.san;

    // source badge (Samay clone moves show where the move came from)
    if (entry.source) {
      const src = String(entry.source).toLowerCase();
      const [cls, label] = SOURCE_BADGE[src] || ["clone", entry.source];
      const badge = document.createElement("span");
      badge.className = `move-badge badge-${cls}`;
      badge.textContent = label;
      cell.appendChild(badge);
    }

    if (i === history.length - 1) cell.classList.add("active");
    moveListEl.appendChild(cell);
  });
  if (history.length % 2 === 1) {
    moveListEl.appendChild(document.createElement("span"));
  }
  moveListEl.scrollTop = moveListEl.scrollHeight;
}

// ── Eval bar ──────────────────────────────────────────────────────────────────
function updateEval(gs) {
  // We don't have engine eval from the API yet, so derive a rough material count
  if (!gs.board) return;
  const VAL = { P: 1, N: 3, B: 3, R: 5, Q: 9, K: 0 };
  let score = 0;
  gs.board.forEach(p => {
    if (!p) return;
    const v = VAL[p[1]] || 0;
    score += p[0] === "w" ? v : -v;
  });
  // clamp to ±20, map to 0-100%
  const pct = 50 + (Math.max(-20, Math.min(20, score)) / 20) * 50;
  evalFill.style.width = pct + "%";
  const abs = Math.abs(score).toFixed(1);
  if (score >= 0) {
    evalLabelW.textContent = "+" + abs;
    evalLabelB.textContent = "";
  } else {
    evalLabelW.textContent = "";
    evalLabelB.textContent = "+" + abs;
  }
}

// ── Material advantage labels ──────────────────────────────────────────────
function updateMaterial(gs) {
  if (!gs.board) return;
  const PIECE_VAL = { P: 1, N: 3, B: 3, R: 5, Q: 9, K: 0 };
  let white = 0, black = 0;
  gs.board.forEach(p => {
    if (!p) return;
    const v = PIECE_VAL[p[1]] || 0;
    if (p[0] === "w") white += v; else black += v;
  });
  const diff = white - black;
  const topIsBlack = !flipped || gs.playerColor !== "b";
  // top = opponent, bottom = player
  const topAdv  = diff < 0 ? "+" + Math.abs(diff) : "";
  const botAdv  = diff > 0 ? "+" + diff : "";
  materialTop.textContent    = topAdv;
  materialBottom.textContent = botAdv;
}

// ── Player name labels ────────────────────────────────────────────────────────
function updateNames(gs) {
  const playerName = "You";
  const opponentName = gs.opponent === "samay" ? "Samay Raina" : "Engine";
  const opponentClass = gs.opponent === "samay" ? "samay-label" : "";

  let topName, botName, topClass, botClass;
  if (!flipped) {
    topName  = gs.playerColor === "w" ? opponentName : playerName;
    botName  = gs.playerColor === "w" ? playerName   : opponentName;
    topClass = gs.playerColor === "w" ? opponentClass : "";
    botClass = gs.playerColor === "w" ? "" : opponentClass;
  } else {
    topName  = gs.playerColor === "b" ? opponentName : playerName;
    botName  = gs.playerColor === "b" ? playerName   : opponentName;
    topClass = gs.playerColor === "b" ? opponentClass : "";
    botClass = gs.playerColor === "b" ? "" : opponentClass;
  }
  nameTop.textContent    = topName;
  nameBottom.textContent = botName;
  nameTop.className    = "player-name " + topClass;
  nameBottom.className = "player-name " + botClass;
}

// ── Game-over overlay ─────────────────────────────────────────────────────────
function checkGameOver(gs) {
  if (!gs.over) {
    overlay.classList.add("hidden");
    return;
  }
  overlay.classList.remove("hidden");
  if (gs.winner === gs.playerColor) {
    overlayIcon.textContent = "🏆";
    overlayTitle.textContent = "You Win!";
  } else if (gs.winner && gs.winner !== gs.playerColor) {
    overlayIcon.textContent = "😔";
    overlayTitle.textContent = "You Lose";
  } else {
    overlayIcon.textContent = "🤝";
    overlayTitle.textContent = "Draw";
  }
  overlaySub.textContent = gs.statusText;
}

// ── Banter ────────────────────────────────────────────────────────────────────
function showBanter(text) {
  if (!text) return;
  banterWrap.classList.remove("hidden");
  // re-trigger animation by replacing the element
  const bubble = banterWrap.querySelector(".banter-bubble");
  bubble.style.animation = "none";
  void bubble.offsetWidth;          // reflow
  bubble.style.animation = "";
  banterText.textContent = text;
}

// ── Full UI update from API response ─────────────────────────────────────────
function applyGameState(gs) {
  state = gs;
  selected = null;
  legalTargets = [];
  renderBoard(gs);
  renderMoveList(gs.history || []);
  updateEval(gs);
  updateMaterial(gs);
  updateNames(gs);
  statusEl.textContent = gs.inCheck ? "⚠ Check!" : (gs.statusText || "");

  // show / hide banter bubble
  if (gs.opponent === "samay" && gs.banter) {
    showBanter(gs.banter);
  } else {
    banterWrap.classList.add("hidden");
  }

  checkGameOver(gs);
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function apiPost(path, body) {
  const r = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}
async function apiGet(path) {
  const r = await fetch(API + path);
  return r.json();
}

// ── Move flow ─────────────────────────────────────────────────────────────────
async function sendMove(uci) {
  const gs = await apiPost("/move", { uci });
  if (gs.error) { console.warn(gs.error); return; }
  applyGameState(gs);
  if (!gs.over) await triggerAI();
}

async function triggerAI() {
  if (!state || state.over) return;
  if (state.turn === state.playerColor) return; // it's the player's turn
  statusEl.textContent = state.opponent === "samay"
    ? "Samay is thinking… 🤔"
    : "Engine thinking…";
  const gs = await apiPost("/ai", {});
  if (gs.error) { console.warn(gs.error); return; }
  applyGameState(gs);
}

// ── Square click handler ──────────────────────────────────────────────────────
function onSquareClick(e) {
  if (!state || state.over) return;
  if (state.turn !== state.playerColor) return; // wait for engine

  const sq = e.currentTarget;
  const idx = parseInt(sq.dataset.idx);
  const sqn = sqName(idx);
  const piece = state.board[idx];

  // Case 1: a legal target is clicked → make the move
  if (selected !== null && legalTargets.includes(idx)) {
    const fromName = sqName(selected);
    const movingPiece = state.board[selected];
    // promotion check
    if (movingPiece && movingPiece[1] === "P") {
      const toRank = parseInt(sqn[1]);
      if ((movingPiece[0] === "w" && toRank === 8) ||
          (movingPiece[0] === "b" && toRank === 1)) {
        pendingPromo = { from: fromName, to: sqn };
        openPromoDialog(movingPiece[0]);
        return;
      }
    }
    sendMove(fromName + sqn);
    selected = null;
    legalTargets = [];
    return;
  }

  // Case 2: click on own piece → select it
  if (piece && piece[0] === state.playerColor) {
    selected = idx;
    const lm = state.legalMoves[sqn] || [];
    legalTargets = lm.map(t => sqIndex(t.slice(0, 2)));
    renderBoard(state);
    return;
  }

  // Case 3: click on empty or enemy with nothing selected → deselect
  selected = null;
  legalTargets = [];
  renderBoard(state);
}

// ── Promotion dialog ──────────────────────────────────────────────────────────
function openPromoDialog(color) {
  const pieces = ["Q", "R", "B", "N"];
  promoChoices.innerHTML = "";
  pieces.forEach(p => {
    const btn = document.createElement("span");
    btn.className = "promo-piece";
    btn.textContent = GLYPH[color + p];
    btn.addEventListener("click", () => {
      promoDialog.classList.add("hidden");
      const { from, to } = pendingPromo;
      pendingPromo = null;
      sendMove(from + to + p.toLowerCase());
    });
    promoChoices.appendChild(btn);
  });
  promoDialog.classList.remove("hidden");
}

// ── Samay mode descriptions ────────────────────────────────────────────────
const MODE_DESCS = {
  casual:   "800-1200 Samay — blunders, impulsive moves, chaos mode.",
  real:     "Authentic Samay — plays exactly like his rated games.",
  peak:     "Locked-in Samay — his best and most careful play.",
  adaptive: "Matches your rating — gets harder as you improve.",
};

function updateOppUI() {
  const oppToggle  = document.querySelector("#opp-pick .toggle.active");
  const issamay    = oppToggle && oppToggle.dataset.val === "samay";
  document.getElementById("engine-opts").classList.toggle("hidden", issamay);
  document.getElementById("samay-opts").classList.toggle("hidden", !issamay);
}

function updateModeDesc() {
  const modeToggle = document.querySelector("#mode-pick .toggle.active");
  const key = modeToggle ? modeToggle.dataset.val : "real";
  document.getElementById("mode-desc").textContent = MODE_DESCS[key] || "";
}

// ── Control bindings ──────────────────────────────────────────────────────────
function getNewGameOptions() {
  const colorToggle = document.querySelector("#color-pick .toggle.active");
  const diffToggle  = document.querySelector("#diff-pick  .toggle.active");
  const oppToggle   = document.querySelector("#opp-pick   .toggle.active");
  const modeToggle  = document.querySelector("#mode-pick  .toggle.active");
  return {
    playerColor: colorToggle ? colorToggle.dataset.val : "w",
    difficulty:  diffToggle  ? parseInt(diffToggle.dataset.val) : 2,
    opponent:    oppToggle   ? oppToggle.dataset.val : "engine",
    cloneMode:   modeToggle  ? modeToggle.dataset.val : "real",
  };
}

async function startNewGame() {
  overlay.classList.add("hidden");
  const opts = getNewGameOptions();
  flipped = opts.playerColor === "b";
  buildBoard();
  const gs = await apiPost("/new", opts);
  applyGameState(gs);
  // show game-start banter immediately for Samay games
  if (gs.opponent === "samay" && gs.banter) showBanter(gs.banter);
  // if playing black, opponent goes first
  if (opts.playerColor === "b") await triggerAI();
}

document.getElementById("btn-new").addEventListener("click", startNewGame);
document.getElementById("overlay-new").addEventListener("click", startNewGame);

document.getElementById("btn-resign").addEventListener("click", async () => {
  if (!state || state.over) return;
  const gs = await apiPost("/resign", {});
  applyGameState(gs);
});

document.getElementById("btn-flip").addEventListener("click", () => {
  flipped = !flipped;
  buildBoard();
  if (state) renderBoard(state);
});

document.getElementById("btn-theme").addEventListener("click", () => {
  const light = document.documentElement.dataset.theme === "light";
  document.documentElement.dataset.theme = light ? "" : "light";
  document.getElementById("btn-theme").textContent = light ? "☀" : "🌙";
});

// toggle buttons
document.querySelectorAll(".toggle-group").forEach(group => {
  group.querySelectorAll(".toggle").forEach(btn => {
    btn.addEventListener("click", () => {
      group.querySelectorAll(".toggle").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      // react to opponent / mode changes immediately
      if (group.id === "opp-pick")  updateOppUI();
      if (group.id === "mode-pick") updateModeDesc();
    });
  });
});

// init visibility
updateOppUI();
updateModeDesc();

// ── Boot ──────────────────────────────────────────────────────────────────────
(async () => {
  try {
    const gs = await apiGet("/state");
    buildBoard();
    applyGameState(gs);
  } catch {
    // server not running yet; just render an empty board
    buildBoard();
    statusEl.textContent = "Start the server: python server.py";
  }
})();
