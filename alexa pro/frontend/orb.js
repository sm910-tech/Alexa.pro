/**
 * orb.js — Animated orb with four distinct states
 * States: 'idle' | 'listening' | 'thinking' | 'speaking'
 *
 * Exposes a global `Orb` object with:
 *   Orb.init(canvasEl)
 *   Orb.setState(state)       — change visual state
 *   Orb.setAudioLevel(0..1)  — drive waveform from mic input
 */

window.Orb = (() => {
  // ── State ──────────────────────────────────────────────────────
  const STATES = {
    idle:      { color1: '#1a6fff', color2: '#06d6f5', glowAlpha: 0.18, pulseSpeed: 0.006, waveAmp: 4  },
    listening: { color1: '#3b9eff', color2: '#06d6f5', glowAlpha: 0.32, pulseSpeed: 0.014, waveAmp: 22 },
    thinking:  { color1: '#7c3aed', color2: '#a78bfa', glowAlpha: 0.26, pulseSpeed: 0.018, waveAmp: 10 },
    speaking:  { color1: '#0ea5e9', color2: '#38bdf8', glowAlpha: 0.28, pulseSpeed: 0.012, waveAmp: 18 },
  };

  let canvas, ctx;
  let width, height, cx, cy, radius;
  let state     = 'idle';
  let current   = { ...STATES.idle };     // interpolated values
  let target    = { ...STATES.idle };
  let phase     = 0;
  let audioLvl  = 0;                      // 0..1 from microphone
  let rafId     = null;
  let particles = [];

  // ── Init ───────────────────────────────────────────────────────
  function init(canvasEl) {
    canvas = canvasEl;
    ctx    = canvas.getContext('2d');
    resize();

    // Spawn ambient particles
    for (let i = 0; i < 28; i++) spawnParticle(true);

    // Canvas click passes to the mic button
    canvas.addEventListener('click', () => {
      const btn = document.getElementById('btn-mic');
      if (btn) btn.click();
    });

    window.addEventListener('resize', resize);
    loop();
  }

  function resize() {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const size = Math.min(canvas.offsetWidth || 260, canvas.offsetHeight || 260);
    canvas.width  = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);
    width  = size;
    height = size;
    cx     = width  / 2;
    cy     = height / 2;
    radius = size   * 0.34;
  }

  // ── Particles ─────────────────────────────────────────────────
  function spawnParticle(random = false) {
    const angle = Math.random() * Math.PI * 2;
    const dist  = radius + 8 + Math.random() * 48;
    particles.push({
      x:     cx + Math.cos(angle) * dist,
      y:     cy + Math.sin(angle) * dist,
      vx:    (Math.random() - 0.5) * 0.25,
      vy:    (Math.random() - 0.5) * 0.25,
      alpha: random ? Math.random() : 0,
      life:  random ? Math.random() * 200 : 0,
      maxLife: 160 + Math.random() * 120,
      size:  0.8 + Math.random() * 1.4,
    });
  }

  function updateParticles() {
    const activeStates = ['listening', 'speaking'];
    const spawnRate = activeStates.includes(state) ? 0.6 : 0.15;

    if (Math.random() < spawnRate) spawnParticle();

    particles = particles.filter(p => {
      p.x += p.vx;
      p.y += p.vy;
      p.life++;
      const half = p.maxLife / 2;
      p.alpha = p.life < half
        ? p.life / half
        : 1 - (p.life - half) / half;
      return p.life < p.maxLife;
    });
  }

  // ── Lerp helpers ──────────────────────────────────────────────
  function lerp(a, b, t) { return a + (b - a) * t; }
  function lerpColor(c1, c2, t) {
    const parse  = h => [parseInt(h.slice(1,3),16), parseInt(h.slice(3,5),16), parseInt(h.slice(5,7),16)];
    const [r1,g1,b1] = parse(c1);
    const [r2,g2,b2] = parse(c2);
    const r = Math.round(lerp(r1,r2,t)), g = Math.round(lerp(g1,g2,t)), b_ = Math.round(lerp(b1,b2,t));
    return `rgb(${r},${g},${b_})`;
  }

  // ── Main render loop ──────────────────────────────────────────
  function loop() {
    rafId = requestAnimationFrame(loop);
    draw();
  }

  function draw() {
    ctx.clearRect(0, 0, width, height);

    const t = 0.035;
    current.glowAlpha  = lerp(current.glowAlpha,  target.glowAlpha,  t * 2);
    current.pulseSpeed = lerp(current.pulseSpeed,  target.pulseSpeed, t);
    current.waveAmp    = lerp(current.waveAmp,     target.waveAmp,    t * 2);

    phase += current.pulseSpeed;

    const c1 = target.color1;
    const c2 = target.color2;

    // ── Outer glow rings ──
    for (let g = 3; g > 0; g--) {
      const gRadius = radius + g * 22 + Math.sin(phase * 0.7) * 5;
      const gAlpha  = current.glowAlpha * (0.25 / g);
      const grad = ctx.createRadialGradient(cx, cy, radius, cx, cy, gRadius);
      grad.addColorStop(0, hexAlpha(c1, gAlpha));
      grad.addColorStop(1, 'transparent');
      ctx.beginPath();
      ctx.arc(cx, cy, gRadius, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();
    }

    // ── Particles ──
    updateParticles();
    particles.forEach(p => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fillStyle = hexAlpha(c2, p.alpha * 0.7);
      ctx.fill();
    });

    // ── Waveform blob ──
    const effectiveAmp = current.waveAmp * (1 + audioLvl * 1.4);
    ctx.beginPath();
    const steps = 80;
    for (let i = 0; i <= steps; i++) {
      const angle = (i / steps) * Math.PI * 2;
      const wave1 = Math.sin(angle * 3  + phase * 2.3) * effectiveAmp * 0.55;
      const wave2 = Math.sin(angle * 5  + phase * 1.7) * effectiveAmp * 0.30;
      const wave3 = Math.sin(angle * 7  + phase * 3.1) * effectiveAmp * 0.15;
      const r     = radius + wave1 + wave2 + wave3;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.closePath();

    // Body gradient
    const bodyGrad = ctx.createRadialGradient(cx - radius * 0.22, cy - radius * 0.22, 0, cx, cy, radius * 1.1);
    bodyGrad.addColorStop(0.0, hexAlpha(c2, 0.92));
    bodyGrad.addColorStop(0.4, hexAlpha(c1, 0.82));
    bodyGrad.addColorStop(1.0, hexAlpha(c1, 0.60));
    ctx.fillStyle   = bodyGrad;
    ctx.shadowColor  = c1;
    ctx.shadowBlur   = 40 + current.glowAlpha * 60;
    ctx.fill();
    ctx.shadowBlur   = 0;

    // Inner highlight
    const hiGrad = ctx.createRadialGradient(cx - radius * 0.3, cy - radius * 0.3, 0, cx, cy, radius * 0.8);
    hiGrad.addColorStop(0, 'rgba(255,255,255,0.22)');
    hiGrad.addColorStop(1, 'transparent');
    ctx.fillStyle = hiGrad;
    ctx.fill();

    // ── Audio waveform ring (listening / speaking) ──
    if (state === 'listening' || state === 'speaking') {
      drawWaveRing(effectiveAmp, c2);
    }

    // Decay audio level
    audioLvl *= 0.88;
  }

  function drawWaveRing(amp, color) {
    const ringR = radius + amp * 0.6 + 18;
    ctx.beginPath();
    const steps = 120;
    for (let i = 0; i <= steps; i++) {
      const angle = (i / steps) * Math.PI * 2;
      const w = Math.sin(angle * 8 + phase * 4) * amp * 0.25 * (1 + audioLvl);
      const r = ringR + w;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.strokeStyle = hexAlpha(color, 0.25);
    ctx.lineWidth   = 1.5;
    ctx.stroke();
  }

  function hexAlpha(hex, alpha) {
    const r = parseInt(hex.slice(1,3), 16);
    const g = parseInt(hex.slice(3,5), 16);
    const b = parseInt(hex.slice(5,7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  // ── Public API ────────────────────────────────────────────────
  function setState(newState) {
    if (!STATES[newState]) return;
    state  = newState;
    target = { ...STATES[newState] };

    const label = document.getElementById('orb-status-label');
    if (label) {
      label.className = `orb-status-label ${newState}`;
      label.textContent = {
        idle:      'Tap to speak',
        listening: 'Listening…',
        thinking:  'Thinking…',
        speaking:  'Speaking',
      }[newState];
    }
  }

  function setAudioLevel(level) {
    audioLvl = Math.max(audioLvl, Math.min(1, level));
  }

  return { init, setState, setAudioLevel };
})();
