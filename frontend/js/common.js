/* 共享 UI 工具 + 语音规范化 */
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function toast(msg, kind) {
  let box = document.getElementById('toast-box');
  if (!box) {
    box = document.createElement('div');
    box.id = 'toast-box';
    box.className = 'toast-box';
    document.body.appendChild(box);
  }
  const colors = { ok: '#16a34a', warn: '#d97706', err: '#dc2626', info: '#1a73e8' };
  const t = document.createElement('div');
  t.style.cssText = `background:#16202c;color:#fff;padding:11px 18px;border-radius:12px;font-size:14px;box-shadow:0 6px 18px rgba(0,0,0,.2);border-left:4px solid ${colors[kind] || colors.info}`;
  t.textContent = msg;
  box.appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

function levelBadge(level) {
  const map = {
    red: '<span class="badge red">危急 · 请立即就医</span>',
    yellow: '<span class="badge yellow">需关注 · 建议就医</span>',
    green: '<span class="badge green">可居家观察</span>',
  };
  return map[level] || '<span class="badge gray">—</span>';
}

/* ---------- 语音：数字规范化（修复 120 念成一百二十） ---------- */
const _CN = '零一二三四五六七八九';
function numToCn(n) {
  n = parseInt(n, 10);
  if (n === 0) return '零';
  const units = ['', '十', '百', '千'];
  const s = String(n);
  let out = '';
  for (let i = 0; i < s.length; i++) {
    const d = +s[i], u = s.length - i - 1;
    if (d === 0) { if (out && !out.endsWith('零')) out += '零'; continue; }
    if (u === 1 && d === 1 && i === 0) { out += '十'; continue; }
    out += _CN[d] + units[u];
  }
  return out.replace(/零+$/, '') || '零';
}

function normalizeForSpeech(text) {
  if (text == null) return '';
  let t = String(text);
  // 血压 120/80 → 一百二十比八十
  t = t.replace(/(\d{2,3})\s*\/\s*(\d{2,3})/g, (m, a, b) => {
    const x = +a, y = +b;
    return (x >= 60 && x <= 260 && y >= 30 && y <= 160) ? numToCn(x) + '比' + numToCn(y) : m;
  });
  // 手机号逐位
  t = t.replace(/(?<!\d)1[3-9]\d{9}(?!\d)/g, (m) => [...m].map(c => c === '1' ? '幺' : _CN[+c]).join(''));
  // 紧急号码按位
  t = t.replace(/(?<!\d)120(?!\d)/g, '幺二零')
       .replace(/(?<!\d)110(?!\d)/g, '幺幺零')
       .replace(/(?<!\d)119(?!\d)/g, '幺幺九')
       .replace(/(?<!\d)122(?!\d)/g, '幺二二');
  return t;
}

/* ---------- 语音输出/输入 ---------- */
let _aiVoiceState = 0; // 0 未知, 1 可用, -1 不可用
const Speech = {
  supported: !!(window.SpeechRecognition || window.webkitSpeechRecognition),

  startRecognition(onResult, onEnd, lang) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast('当前浏览器不支持语音识别，请用 Chrome/Edge', 'warn'); if (onEnd) onEnd(); return null; }
    const rec = new SR();
    rec.lang = lang || 'zh-CN'; rec.interimResults = true; rec.continuous = false;
    rec.onresult = (e) => {
      let txt = '';
      for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript;
      if (onResult) onResult(txt);
    };
    rec.onend = () => { if (onEnd) onEnd(); };
    rec.onerror = (e) => { if (e.error !== 'no-speech' && e.error !== 'aborted') toast('语音识别失败：' + e.error, 'warn'); if (onEnd) onEnd(); };
    try { rec.start(); } catch (e) {}
    return rec;
  },

  async speak(text) {
    const norm = normalizeForSpeech(text);
    if (!norm) return;
    if (_aiVoiceState !== -1) {
      try {
        const r = await API.voiceTts(norm);
        if (r && r.audio) {
          _aiVoiceState = 1;
          const a = new Audio('data:' + (r.mime || 'audio/mpeg') + ';base64,' + r.audio);
          a.play();
          return;
        }
      } catch (e) { _aiVoiceState = -1; }
    }
    this.browserSpeak(norm);
  },

  browserSpeak(text) {
    if (!window.speechSynthesis) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'zh-CN'; u.rate = 0.95;
      window.speechSynthesis.speak(u);
    } catch (e) {}
  },

  stop() { if (window.speechSynthesis) window.speechSynthesis.cancel(); },
};

/* ---------- 登录态与外壳 ---------- */
function requireLogin() {
  if (!API.token()) { location.href = '/login'; return false; }
  return true;
}

async function loadMe() {
  const m = await API.me();
  localStorage.setItem('medagent_role', m.account.role);
  localStorage.setItem('medagent_name', m.account.display_name || m.account.username);
  if (m.bindings && m.bindings.length) setCurrentUserId(m.bindings[0].user_id);
  return m;
}

function logout() {
  API.logout().catch(() => {}).finally(() => {
    API.clearToken();
    localStorage.removeItem('medagent_role');
    localStorage.removeItem('medagent_name');
    location.href = '/login';
  });
}

const ROLE_HOME = { user: '/user', guardian: '/guardian', doctor: '/doctor' };
const ROLE_LABEL = { user: '使用者', guardian: '监护人', doctor: '医生' };
function roleHome(role) { return ROLE_HOME[role] || '/login'; }

// 角色锁定：登录后只能使用本身份的界面，切换身份需退出登录
function requireRole(expected) {
  if (!API.token()) { location.replace('/login'); return false; }
  const role = localStorage.getItem('medagent_role') || 'user';
  if (role !== expected) { location.replace(roleHome(role)); return false; }
  return true;
}

function renderSidebar(role, active) {
  const navItems = {
    user: [{ id: 'user', href: '/user', icon: '💬', label: 'AI 智能导诊' }],
    guardian: [{ id: 'guardian', href: '/guardian', icon: '🛡️', label: '监护人看板' }],
    doctor: [{ id: 'doctor', href: '/doctor', icon: '🩺', label: '医生工作台' }],
  };
  const items = navItems[role] || [];
  const name = localStorage.getItem('medagent_name') || '';
  const icon = { user: '👴', guardian: '👨‍👩‍👧', doctor: '🩺' }[role] || '👤';
  const el = document.getElementById('sidebar');
  if (!el) return;
  el.innerHTML = `
    <div class="brand"><div class="logo">✚</div>
      <div><b>健康守护</b><span>MedAgent</span></div></div>
    <div class="role-chip">${icon} ${ROLE_LABEL[role] || ''}身份</div>
    <nav class="nav">
      <div class="nav-title">本系统</div>
      ${items.map(i => `<a href="${i.href}" class="${i.id === active ? 'active' : ''}"><span class="ico">${i.icon}</span>${i.label}</a>`).join('')}
    </nav>
    <div class="side-user">
      <div class="name">${esc(name)}</div>
      <div class="meta">当前身份：${ROLE_LABEL[role] || ''}</div>
      <button class="logout" onclick="logout()">↩ 退出登录后切换身份</button>
    </div>
    <div class="foot">© MedAgent · 非诊断工具</div>`;
}

function renderHero(role) {
  const content = document.querySelector('.content');
  if (!content || content.querySelector('.hero')) return;
  const name = localStorage.getItem('medagent_name') || '';
  const conf = {
    user: { emoji: '🌿', title: `您好，${esc(name)}`, sub: '今天也要照顾好自己，哪里不舒服随时告诉我' },
    guardian: { emoji: '🛡️', title: `${esc(name)}，欢迎回来`, sub: '实时掌握家人健康状况，安排今日照护' },
    doctor: { emoji: '🩺', title: `${esc(name)}，欢迎回来`, sub: '优先处理异常患者，查看随访与问诊' },
  }[role] || { emoji: '👋', title: '欢迎', sub: '' };
  const hero = document.createElement('div');
  hero.className = 'hero' + (role === 'doctor' ? ' teal' : '');
  hero.innerHTML = `<div><h1>${conf.title}</h1><p>${conf.sub}</p></div><div class="big-emoji">${conf.emoji}</div>`;
  content.insertBefore(hero, content.firstChild);
}
