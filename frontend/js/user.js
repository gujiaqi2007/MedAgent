/* AI 智能导诊（使用者端） */
(function () {
  if (!requireLogin()) return;
  const chatBox = document.getElementById('chat-box');
  const input = document.getElementById('msg-input');
  const sendBtn = document.getElementById('send-btn');
  const micBtn = document.getElementById('mic-btn');
  const sosBtn = document.getElementById('sos-btn');
  const metricType = document.getElementById('metric-type');
  const metricValue = document.getElementById('metric-value');
  const saveMetric = document.getElementById('save-metric');
  const syncBtn = document.getElementById('sync-btn');
  const syncStatus = document.getElementById('sync-status');
  const dueList = document.getElementById('due-list');

  let sessionId = null, recognizing = false;

  function addMe(text) {
    const d = document.createElement('div');
    d.className = 'msg me';
    d.innerHTML = `<div class="avatar">🙂</div><div class="bubble">${esc(text)}</div>`;
    chatBox.appendChild(d);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // 追问卡片：点击问题 → 展开选项(+其他)；点选项才作为回答发送
  function renderFollowups(container, followups) {
    container.innerHTML = '';
    (followups || []).forEach(f => {
      const div = document.createElement('div');
      div.className = 'fq';
      div.innerHTML = `<div class="q">${esc(f.q)}<span class="hint">点击选择</span></div><div class="opts" style="display:none"></div>`;
      const opts = div.querySelector('.opts');
      div.querySelector('.q').onclick = () => {
        if (opts.style.display === 'flex') { opts.style.display = 'none'; return; }
        opts.style.display = 'flex';
        opts.innerHTML = '';
        (f.options || ['是', '否', '不清楚']).forEach(o => {
          const b = document.createElement('button');
          b.className = 'opt';
          b.textContent = o;
          b.onclick = () => send(o);
          opts.appendChild(b);
        });
        const other = document.createElement('button');
        other.className = 'opt other';
        other.textContent = '其他';
        other.onclick = () => { input.focus(); input.placeholder = '请直接输入您的回答…'; };
        opts.appendChild(other);
      };
      container.appendChild(div);
    });
  }

  function addAgent(r) {
    const d = document.createElement('div');
    d.className = 'msg ai';
    d.innerHTML = `<div class="avatar">🤖</div>
      <div class="bubble">
        <div class="row" style="margin-bottom:6px">${levelBadge(r.triage_level)} <b>${esc(r.title)}</b></div>
        ${r.plain ? `<div class="plain">${esc(r.plain)}</div>` : ''}
        ${r.advice ? `<div class="advice">${esc(r.advice)}</div>` : ''}
        ${r.source ? `<div class="src">依据：${esc(r.source)}</div>` : ''}
        <div class="followups"></div>
      </div>`;
    chatBox.appendChild(d);
    renderFollowups(d.querySelector('.followups'), r.followups);
    chatBox.scrollTop = chatBox.scrollHeight;
    Speech.speak(r.title + '。' + (r.plain || '') + ' ' + (r.advice || ''));
  }

  async function send(msg) {
    msg = (msg || '').trim();
    if (!msg) return;
    addMe(msg);
    input.value = '';
    sendBtn.disabled = true;
    try {
      const r = await API.chat(currentUserId(), msg, sessionId);
      sessionId = r.session_id;
      addAgent(r);
      if (r.suggest_120) toast('已建议立即拨打 120，请尽快处理', 'err');
      if (r.notified_guardian) toast('已通知监护人', 'info');
      loadDue();
    } catch (e) {
      toast('发送失败：' + e.message, 'err');
    } finally {
      sendBtn.disabled = false;
    }
  }

  sendBtn.onclick = () => send(input.value);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') send(input.value); });

  micBtn.onclick = () => {
    if (recognizing) return;
    recognizing = true;
    micBtn.classList.add('rec');
    Speech.startRecognition(
      (txt) => { input.value = txt; },
      () => { recognizing = false; micBtn.classList.remove('rec'); if (input.value.trim()) send(input.value); }
    );
  };

  sosBtn.onclick = async () => {
    if (!confirm('确定紧急呼救吗？将立即通知监护人。')) return;
    try {
      await API.sos(currentUserId());
      toast('紧急呼救已发出', 'err');
      Speech.speak('已为您发出紧急呼救，请保持电话畅通。');
    } catch (e) { toast('呼救失败：' + e.message, 'err'); }
  };

  async function loadDue() {
    try {
      const r = await API.reminders(currentUserId());
      const due = r.reminders.filter(x => x.due_now);
      if (!due.length) { dueList.textContent = '今日暂无待办提醒。'; return; }
      dueList.innerHTML = due.map(d => `<div class="alert-item info" style="margin-bottom:8px">
        <div><div class="t">${esc(d.title)}</div><div class="m">${esc(d.detail || '')} · ${esc(d.cron)}</div></div>
        <button class="btn green sm" onclick="window._take('${d.id}')">已完成</button></div>`).join('');
    } catch (e) { dueList.textContent = '加载失败'; }
  }
  window._take = async (id) => {
    await API.takeReminder(id, currentUserId());
    toast('已记录', 'ok');
    loadDue();
  };

  saveMetric.onclick = async () => {
    const type = metricType.value;
    const value = parseFloat(metricValue.value);
    if (isNaN(value)) { toast('请输入数值', 'warn'); return; }
    try {
      await API.addMetric({ user_id: currentUserId(), metrics: [{ type, value, source: 'manual' }] });
      metricValue.value = '';
      toast('已保存', 'ok');
    } catch (e) { toast('保存失败：' + e.message, 'err'); }
  };

  syncBtn.onclick = async () => {
    try {
      const r = await API.syncDevice(currentUserId(), true);
      syncStatus.textContent = '已同步 ' + r.inserted + ' 条';
      toast('设备数据已同步', 'ok');
    } catch (e) { toast('同步失败：' + e.message, 'err'); }
  };

  (async function init() {
    try { await loadMe(); } catch (e) {}
    const role = localStorage.getItem('medagent_role') || 'user';
    renderSidebar(role, 'user');
    const d = document.createElement('div');
    d.className = 'msg ai';
    d.innerHTML = `<div class="avatar">🤖</div><div class="bubble"><div class="plain">您好，我是健康小助手。哪里不舒服，可以直接说，也可以点 🎤 说话。</div></div>`;
    chatBox.appendChild(d);
    loadDue();
  })();
})();
