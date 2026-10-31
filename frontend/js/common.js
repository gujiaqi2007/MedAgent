/* 共享 UI 工具 */
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
    box.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(box);
  }
  const t = document.createElement('div');
  const colors = { ok: '#16a34a', warn: '#d97706', err: '#dc2626', info: '#2563eb' };
  t.style.cssText = `background:#1f2d3d;color:#fff;padding:12px 18px;border-radius:12px;font-size:15px;box-shadow:0 6px 18px rgba(0,0,0,.2);border-left:4px solid ${colors[kind] || '#2563eb'}`;
  t.textContent = msg;
  box.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

function levelBadge(level) {
  const map = { red: '<span class="badge red">危急 · 请就医</span>', yellow: '<span class="badge yellow">需关注</span>', green: '<span class="badge green">可居家观察</span>' };
  return map[level] || '<span class="badge gray">—</span>';
}

// 轻量 Markdown → HTML（仅支持常见格式，输出已做 HTML 转义）
function renderMarkdown(text) {
  if (!text) return '';
  return text
    // 先转义 HTML 特殊字符
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // 再处理 Markdown 标记
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*([^*]|$)/g, '$1<em>$2</em>$3')
    .replace(/`{1,3}([^`]*?)`{1,3}/g, '<code>$1</code>')
    .replace(/^#{1,6}\s*(.*)$/gim, '<strong>$1</strong>')
    .replace(/^[-*+]\s+(.*)$/gim, '• $1')
    // 换行
    .replace(/\n/g, '<br>');
}

// 语音：浏览器 Web Speech API（ASR + TTS）
const Speech = {
  supported: !!(window.SpeechRecognition || window.webkitSpeechRecognition) || !!window.speechSynthesis,

  startRecognition(onResult, onEnd) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast('当前浏览器不支持语音识别，请使用 Chrome/Edge', 'warn'); return null; }
    const rec = new SR();
    rec.lang = 'zh-CN';
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (e) => {
      let txt = '';
      for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript;
      if (onResult) onResult(txt);
    };
    rec.onend = () => { if (onEnd) onEnd(); };
    rec.onerror = (e) => {
      if (e.error !== 'no-speech' && e.error !== 'aborted') toast('语音识别失败：' + e.error, 'warn');
      if (onEnd) onEnd();
    };
    try { rec.start(); } catch (e) {}
    return rec;
  },

  speak(text) {
    if (!window.speechSynthesis) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'zh-CN';
      u.rate = 0.95;
      window.speechSynthesis.speak(u);
    } catch (e) {}
  },

  stopSpeak() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  },
};
