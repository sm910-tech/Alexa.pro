/**
 * app.js — Main application controller
 *
 * Responsibilities:
 *  • Navigation between views
 *  • Sending messages to the backend
 *  • Rendering transcripts and conversation history
 *  • Dashboard widgets (weather, clock, reminders, timers, smart home)
 *  • Settings persistence
 *  • Toast notifications
 */

/* ─────────────────────────────────────────────────────────────────
   CONFIG
───────────────────────────────────────────────────────────────── */
const DEFAULT_BACKEND_URL = 'https://alexa-pro.onrender.com';

const Config = {
  get backendUrl() {
    const saved = (localStorage.getItem('backend_url') || '').trim();
    // Ignore a stale localhost setting when this site is hosted online.
    if (saved && !/^https?:\/\/localhost(?::\d+)?$/i.test(saved)) {
      return saved.replace(/\/+$/, '');
    }
    return DEFAULT_BACKEND_URL;
  },
  set backendUrl(value) {
    const normalized = String(value || '').trim().replace(/\/+$/, '');
    if (!normalized) {
      localStorage.removeItem('backend_url');
      return;
    }
    localStorage.setItem('backend_url', normalized);
  },
};

function readStoredJson(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch (error) {
    console.warn(`Ignoring invalid localStorage data for "${key}".`, error);
    return fallback;
  }
}

/* ─────────────────────────────────────────────────────────────────
   STATE
───────────────────────────────────────────────────────────────── */
const State = {
  conversationHistory: [],
  reminders:           readStoredJson('reminders', []),
  timers:              [],
  userName:            localStorage.getItem('user_name') || '',
};

/* ─────────────────────────────────────────────────────────────────
   INIT
───────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initOrb();
  initVoice();
  initNavigation();
  initHomeControls();
  initDashboard();
  initRemindersView();
  initSettings();
  startClocks();
  checkBackendHealth();
});

/* ─────────────────────────────────────────────────────────────────
   ORB
───────────────────────────────────────────────────────────────── */
function initOrb() {
  const canvas = document.getElementById('orb-canvas');
  if (canvas) Orb.init(canvas);
}

/* ─────────────────────────────────────────────────────────────────
   VOICE
───────────────────────────────────────────────────────────────── */
function initVoice() {
  Voice.init(
    (transcript) => {
      // Called with the final recognized text
      handleUserMessage(transcript);
    },
    (errorMsg) => {
      toast(errorMsg, 'error');
      Orb.setState('idle');
      setMicState(false);
    }
  );
}

/* ─────────────────────────────────────────────────────────────────
   NAVIGATION
───────────────────────────────────────────────────────────────── */
function initNavigation() {
  document.querySelectorAll('.nav-item[data-view]').forEach(btn => {
    btn.addEventListener('click', () => navigateTo(btn.dataset.view));
  });

  document.getElementById('sidebar-toggle')?.addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('collapsed');
  });
}

function navigateTo(viewName) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));

  const view = document.getElementById(`view-${viewName}`);
  if (view) view.classList.add('active');

  const btn = document.querySelector(`.nav-item[data-view="${viewName}"]`);
  if (btn) btn.classList.add('active');

  // Refresh data on navigation
  if (viewName === 'dashboard') refreshDashboard();
  if (viewName === 'reminders') renderRemindersView();
  if (viewName === 'history')   renderHistory();
}

/* ─────────────────────────────────────────────────────────────────
   HOME CONTROLS
───────────────────────────────────────────────────────────────── */
function initHomeControls() {
  const btnMic      = document.getElementById('btn-mic');
  const btnKeyboard = document.getElementById('btn-keyboard');
  const btnMute     = document.getElementById('btn-mute');
  const btnSend     = document.getElementById('btn-send');
  const btnCloseKB  = document.getElementById('btn-close-keyboard');
  const textInput   = document.getElementById('text-input');
  const textArea    = document.getElementById('text-input-area');

  btnMic?.addEventListener('click', () => {
    if (Voice.isListening) {
      Voice.stopListening();
      setMicState(false);
    } else {
      Voice.startListening();
      setMicState(true);
    }
  });

  btnKeyboard?.addEventListener('click', () => {
    textArea.hidden = false;
    textInput.focus();
  });

  btnCloseKB?.addEventListener('click', () => {
    textArea.hidden = true;
  });

  btnMute?.addEventListener('click', () => {
    if (Voice.isMuted) { Voice.unmute(); btnMute.title = 'Mute'; }
    else               { Voice.mute();   btnMute.title = 'Unmute'; }
  });

  btnSend?.addEventListener('click', sendTextInput);
  textInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendTextInput();
    }
  });
}

function sendTextInput() {
  const input = document.getElementById('text-input');
  const text  = input?.value.trim();
  if (!text) return;
  input.value = '';
  handleUserMessage(text);
}

function setMicState(on) {
  const btn = document.getElementById('btn-mic');
  if (!btn) return;
  btn.classList.toggle('listening', on);
  btn.setAttribute('aria-label', on ? 'Stop listening' : 'Start listening');
}

/* ─────────────────────────────────────────────────────────────────
   MESSAGE PIPELINE
───────────────────────────────────────────────────────────────── */
async function handleUserMessage(text) {
  if (!text) return;
  setMicState(false);

  // Show user message
  showTranscript('user', text);

  // Add to history
  State.conversationHistory.push({ role: 'user', content: text });

  // Thinking state
  Orb.setState('thinking');
  showTranscript('assistant', '…');

  try {
    const response = await sendToBackend(text);
    const reply    = response.reply || 'I didn\'t get a response. Is the backend running?';

    // Update transcript
    showTranscript('assistant', reply);

    // Add to history
    State.conversationHistory.push({ role: 'assistant', content: reply });
    saveHistoryEntry(text, reply);

    // Handle tool results (e.g. reminders created)
    if (response.tool_results) handleToolResults(response.tool_results);

    // Speak the reply
    Voice.speak(reply, () => {
      Orb.setState('idle');
    });

  } catch (err) {
    const errMsg = err.message || 'Could not reach the backend. Start it with: uvicorn main:app --reload';
    showTranscript('assistant', errMsg);
    Orb.setState('idle');
    toast('Backend unreachable', 'error');
  }
}

async function sendToBackend(message) {
  const baseUrl = Config.backendUrl.replace(/\/+$/, '');
  let res;

  try {
    res = await fetch(`${baseUrl}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        history: State.conversationHistory.slice(-20),
      }),
      signal: AbortSignal.timeout(45000),
    });
  } catch (error) {
    if (error.name === 'TimeoutError' || error.name === 'AbortError') {
      throw new Error('The backend took too long to respond. Try again in a moment.');
    }
    throw new Error(`Could not reach ${baseUrl}. Check the backend URL and connection.`);
  }

  const body = await res.text();
  let data;
  try {
    data = body ? JSON.parse(body) : {};
  } catch {
    data = { detail: body };
  }

  if (!res.ok) {
    const detail = typeof data.detail === 'string'
      ? data.detail
      : JSON.stringify(data.detail || data || `HTTP ${res.status}`);
    throw new Error(`Backend error ${res.status}: ${detail}`);
  }

  if (!data || typeof data.reply !== 'string') {
    throw new Error('Backend returned an invalid response: missing a text reply.');
  }

  return data;
}

function handleToolResults(results) {
  if (results.reminders_updated) {
    State.reminders = results.reminders || State.reminders;
    saveReminders();
    renderDashboardReminders();
  }
  if (results.timer_set) {
    addTimer(results.timer_set.label, results.timer_set.seconds);
  }
}

/* ─────────────────────────────────────────────────────────────────
   TRANSCRIPT
───────────────────────────────────────────────────────────────── */
function showTranscript(role, text) {
  const el = document.getElementById(`transcript-${role}`);
  if (!el) return;
  el.textContent = text;
  el.hidden = false;
}

/* ─────────────────────────────────────────────────────────────────
   CLOCKS
───────────────────────────────────────────────────────────────── */
function startClocks() {
  updateClocks();
  setInterval(updateClocks, 1000);
}

function updateClocks() {
  const now = new Date();

  // Home clock
  const homeTime = document.getElementById('home-time');
  if (homeTime) homeTime.textContent = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });

  const homeDate = document.getElementById('home-date');
  if (homeDate) homeDate.textContent = now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });

  const homeGreeting = document.getElementById('home-greeting');
  if (homeGreeting) {
    const name = State.userName ? `, ${State.userName}` : '';
    const hour = now.getHours();
    const greet = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
    homeGreeting.textContent = `${greet}${name}`;
  }

  // Dashboard clocks
  const dashTime = document.getElementById('dash-time');
  if (dashTime) dashTime.textContent = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

  const timeDisplay = document.getElementById('time-display');
  if (timeDisplay) timeDisplay.textContent = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  const dateDisplay = document.getElementById('date-display');
  if (dateDisplay) dateDisplay.textContent = now.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}

/* ─────────────────────────────────────────────────────────────────
   DASHBOARD
───────────────────────────────────────────────────────────────── */
function initDashboard() {
  // Quick action buttons
  document.querySelectorAll('.quick-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const query = btn.dataset.query;
      if (!query) return;
      navigateTo('home');
      setTimeout(() => handleUserMessage(query), 200);
    });
  });

  // Smart home toggles
  document.querySelectorAll('.sh-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const on = btn.classList.contains('off');
      btn.classList.toggle('off', !on);
      btn.querySelector('.sh-state').textContent = on ? 'On' : 'Off';
      btn.dataset.state = on ? 'on' : 'off';
      toast(`${btn.dataset.device} turned ${on ? 'on' : 'off'}`, 'info');
    });
  });

  // Dashboard add reminder
  document.getElementById('dash-add-reminder')?.addEventListener('click', () => navigateTo('reminders'));
  document.getElementById('dash-add-timer')?.addEventListener('click', promptTimer);

  refreshDashboard();
}

async function refreshDashboard() {
  fetchWeather();
  renderDashboardReminders();
}

async function fetchWeather() {
  try {
    const res = await fetch(`${Config.backendUrl}/weather`, {
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) throw new Error(`Weather request failed (${res.status})`);
    const data = await res.json();

    const icon = document.getElementById('weather-icon');
    const temp = document.getElementById('weather-temp');
    const desc = document.getElementById('weather-desc');
    const meta = document.getElementById('weather-meta');

    if (icon) icon.textContent = data.icon || '⛅';
    if (temp) temp.textContent = data.temp || '--°';
    if (desc) desc.textContent = data.description || 'Weather unavailable';
    if (meta) meta.textContent = data.location || '';
  } catch (error) {
    console.warn('Weather could not be loaded:', error);
    const desc = document.getElementById('weather-desc');
    if (desc) desc.textContent = 'Weather unavailable';
  }
}

function renderDashboardReminders() {
  const list = document.getElementById('dash-reminder-list');
  if (!list) return;

  const pending = State.reminders.filter(r => !r.done).slice(0, 4);
  if (pending.length === 0) {
    list.innerHTML = '<li class="reminder-empty">No reminders</li>';
    return;
  }

  list.innerHTML = pending.map(r => `
    <li class="reminder-item">
      <input type="checkbox" data-id="${r.id}" ${r.done ? 'checked' : ''} />
      <span class="ri-text">${escHtml(r.text)}</span>
      ${r.time ? `<span class="ri-time">${formatTime(r.time)}</span>` : ''}
    </li>
  `).join('');

  list.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', () => toggleReminder(cb.dataset.id));
  });
}

/* ─────────────────────────────────────────────────────────────────
   TIMERS
───────────────────────────────────────────────────────────────── */
function promptTimer() {
  const label   = prompt('Timer label (e.g. "Tea"):') || 'Timer';
  const minutes = parseFloat(prompt('Duration in minutes:'));
  if (isNaN(minutes) || minutes <= 0) return;
  addTimer(label, Math.round(minutes * 60));
}

function addTimer(label, seconds) {
  const id = Date.now();
  State.timers.push({ id, label, remaining: seconds });
  toast(`⏱ Timer set: ${label} (${fmtSecs(seconds)})`, 'info');
  renderTimers();

  const interval = setInterval(() => {
    const t = State.timers.find(t => t.id === id);
    if (!t) { clearInterval(interval); return; }
    t.remaining--;
    renderTimers();
    if (t.remaining <= 0) {
      clearInterval(interval);
      State.timers = State.timers.filter(t => t.id !== id);
      renderTimers();
      toast(`⏰ "${label}" timer is done!`, 'success');
      Voice.speak(`Your ${label} timer is done.`);
    }
  }, 1000);
}

function renderTimers() {
  const container = document.getElementById('timer-list');
  if (!container) return;

  if (State.timers.length === 0) {
    container.innerHTML = '<div class="timer-empty">No active timers</div>';
    return;
  }

  container.innerHTML = State.timers.map(t => `
    <div class="timer-item" data-id="${t.id}">
      <span class="t-name">${escHtml(t.label)}</span>
      <span class="t-count">${fmtSecs(t.remaining)}</span>
      <button class="t-del" data-id="${t.id}" title="Cancel">✕</button>
    </div>
  `).join('');

  container.querySelectorAll('.t-del').forEach(btn => {
    btn.addEventListener('click', () => {
      State.timers = State.timers.filter(t => t.id !== parseInt(btn.dataset.id));
      renderTimers();
    });
  });
}

function fmtSecs(s) {
  const m = Math.floor(s / 60), sec = s % 60;
  return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
}

/* ─────────────────────────────────────────────────────────────────
   REMINDERS
───────────────────────────────────────────────────────────────── */
function initRemindersView() {
  document.getElementById('btn-add-reminder')?.addEventListener('click', () => {
    document.getElementById('reminder-form').hidden = false;
    document.getElementById('reminder-text-input').focus();
  });

  document.getElementById('btn-save-reminder')?.addEventListener('click', saveNewReminder);
  document.getElementById('btn-cancel-reminder')?.addEventListener('click', () => {
    document.getElementById('reminder-form').hidden = true;
  });
}

function saveNewReminder() {
  const text = document.getElementById('reminder-text-input').value.trim();
  const time = document.getElementById('reminder-time-input').value;
  if (!text) { toast('Enter reminder text', 'error'); return; }

  const reminder = { id: Date.now().toString(), text, time: time || null, done: false };
  State.reminders.push(reminder);
  saveReminders();
  renderRemindersView();
  renderDashboardReminders();

  document.getElementById('reminder-text-input').value = '';
  document.getElementById('reminder-time-input').value = '';
  document.getElementById('reminder-form').hidden = true;
  toast('Reminder saved', 'success');
}

function toggleReminder(id) {
  const r = State.reminders.find(r => r.id === String(id));
  if (r) r.done = !r.done;
  saveReminders();
  renderRemindersView();
  renderDashboardReminders();
}

function saveReminders() {
  localStorage.setItem('reminders', JSON.stringify(State.reminders));
}

function renderRemindersView() {
  const list = document.getElementById('reminders-full-list');
  if (!list) return;

  if (State.reminders.length === 0) {
    list.innerHTML = '<div class="reminder-empty">No reminders yet. Add your first one.</div>';
    return;
  }

  list.innerHTML = State.reminders.map(r => `
    <div class="full-reminder-item ${r.done ? 'done' : ''}" data-id="${r.id}">
      <input type="checkbox" data-id="${r.id}" ${r.done ? 'checked' : ''} />
      <span class="fri-text">${escHtml(r.text)}</span>
      ${r.time ? `<span class="fri-time">${formatTime(r.time)}</span>` : ''}
      <button class="fri-del" data-id="${r.id}" title="Delete">✕</button>
    </div>
  `).join('');

  list.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', () => toggleReminder(cb.dataset.id));
  });
  list.querySelectorAll('.fri-del').forEach(btn => {
    btn.addEventListener('click', () => {
      State.reminders = State.reminders.filter(r => r.id !== btn.dataset.id);
      saveReminders();
      renderRemindersView();
      renderDashboardReminders();
    });
  });
}

/* ─────────────────────────────────────────────────────────────────
   HISTORY
───────────────────────────────────────────────────────────────── */
function saveHistoryEntry(user, assistant) {
  const history = JSON.parse(localStorage.getItem('history') || '[]');
  history.unshift({ user, assistant, time: new Date().toISOString() });
  if (history.length > 100) history.length = 100;
  localStorage.setItem('history', JSON.stringify(history));
}

function renderHistory() {
  const list = document.getElementById('history-list');
  if (!list) return;
  const history = JSON.parse(localStorage.getItem('history') || '[]');

  if (history.length === 0) {
    list.innerHTML = '<div class="history-empty">No conversations yet. Start talking!</div>';
    return;
  }

  list.innerHTML = history.map(entry => `
    <div class="history-entry">
      <div class="history-entry-meta">${formatDateTime(entry.time)}</div>
      <div class="history-entry-user">${escHtml(entry.user)}</div>
      <div class="history-entry-assistant">${escHtml(entry.assistant)}</div>
    </div>
  `).join('');
}

document.getElementById('btn-clear-history')?.addEventListener('click', () => {
  if (!confirm('Clear all conversation history?')) return;
  localStorage.removeItem('history');
  renderHistory();
  toast('History cleared', 'info');
});

/* ─────────────────────────────────────────────────────────────────
   SETTINGS
───────────────────────────────────────────────────────────────── */
function initSettings() {
  // Populate voice list
  Voice.populateVoiceList(document.getElementById('setting-tts'));

  // Rate
  const rateSlider = document.getElementById('setting-rate');
  const rateVal    = document.getElementById('setting-rate-val');
  rateSlider?.addEventListener('input', () => {
    const v = parseFloat(rateSlider.value);
    rateVal.textContent = `${v.toFixed(1)}×`;
    Voice.setRate(v);
    localStorage.setItem('voice_rate', v);
  });
  const savedRate = parseFloat(localStorage.getItem('voice_rate') || '1');
  if (rateSlider) { rateSlider.value = savedRate; rateVal.textContent = `${savedRate.toFixed(1)}×`; }
  Voice.setRate(savedRate);

  // Pitch
  const pitchSlider = document.getElementById('setting-pitch');
  const pitchVal    = document.getElementById('setting-pitch-val');
  pitchSlider?.addEventListener('input', () => {
    const v = parseFloat(pitchSlider.value);
    pitchVal.textContent = v.toFixed(1);
    Voice.setPitch(v);
    localStorage.setItem('voice_pitch', v);
  });
  const savedPitch = parseFloat(localStorage.getItem('voice_pitch') || '1');
  if (pitchSlider) { pitchSlider.value = savedPitch; pitchVal.textContent = savedPitch.toFixed(1); }
  Voice.setPitch(savedPitch);

  // User name
  const nameInput = document.getElementById('setting-name');
  if (nameInput) {
    nameInput.value = State.userName;
    nameInput.addEventListener('input', () => {
      State.userName = nameInput.value.trim();
      localStorage.setItem('user_name', State.userName);
    });
  }

  // Backend URL
  const urlInput = document.getElementById('setting-backend-url');
  if (urlInput) {
    urlInput.value = Config.backendUrl;
    urlInput.addEventListener('change', () => {
      Config.backendUrl = urlInput.value.trim().replace(/\/$/, '');
    });
  }

  // Test backend
  document.getElementById('btn-test-backend')?.addEventListener('click', async () => {
    const result = document.getElementById('backend-test-result');
    result.textContent = 'Testing…';
    result.className   = 'backend-test-result';
    try {
      const res = await fetch(`${Config.backendUrl}/health`, {
        signal: AbortSignal.timeout(8000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      result.textContent = `✓ Connected — ${data.message || 'Backend OK'}`;
      result.className = 'backend-test-result ok';
    } catch (e) {
      result.textContent = `✗ Connection failed: ${e.message || 'check URL and backend status'}`;
      result.className = 'backend-test-result err';
    }
  });
}

/* ─────────────────────────────────────────────────────────────────
   BACKEND HEALTH
───────────────────────────────────────────────────────────────── */
async function checkBackendHealth() {
  const dot  = document.getElementById('status-dot');
  const text = document.getElementById('status-text');

  const check = async () => {
    try {
      const res = await fetch(`${Config.backendUrl}/health`, {
        signal: AbortSignal.timeout(8000),
      });
      if (res.ok) {
        if (dot) dot.className = 'status-dot connected';
        if (text) text.textContent = 'Connected';
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch {
      if (dot) dot.className = 'status-dot error';
      if (text) text.textContent = 'Offline';
    }
  };

  await check();
  setInterval(check, 30_000);
}

/* ─────────────────────────────────────────────────────────────────
   TOAST
───────────────────────────────────────────────────────────────── */
function toast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className   = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

/* ─────────────────────────────────────────────────────────────────
   UTILS
───────────────────────────────────────────────────────────────── */
function escHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#x27;');
}

function formatTime(isoOrLocal) {
  try {
    const d = new Date(isoOrLocal);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return isoOrLocal; }
}

function formatDateTime(iso) {
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

// Expose toast globally for console debugging
window.toast = toast;
