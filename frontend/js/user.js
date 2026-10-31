/* 使用者模式逻辑 */
(function () {
  const chatBox = document.getElementById('chat-box');
  const chipsEl = document.getElementById('chips');
  const input = document.getElementById('msg-input');
  const sendBtn = document.getElementById('send-btn');
  const micBtn = document.getElementById('mic-btn');
  const sosBtn = document.getElementById('sos-btn');
  const voiceOut = document.getElementById('voice-out');
  const metricType = document.getElementById('metric-type');
  const metricValue = document.getElementById('metric-value');
  const saveMetric = document.getElementById('save-metric');
  const dueList = document.getElementById('due-list');

  let sessionId = null;
  let recognizing = false;

  function addBubble(role, html, triageLevel) {
    const div = document.createElement('div');
    div.className = 'bubble ' + role;
    div.innerHTML = html + (triageLevel ? `<div class="triage">${levelBadge(triageLevel)}</div>` : '');
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
    return div;
  }

  function setChips(followups) {
    chipsEl.innerHTML = '';
    (followups || []).forEach(q => {
      const c = document.createElement('button');
      c.className = 'chip';
      c.textContent = q;
      c.onclick = () => { input.value = q; send(); };
      chipsEl.appendChild(c);
    });
  }

  async function send() {
    const msg = input.value.trim();
    if (!msg) return;
    addBubble('user', esc(msg));
    input.value = '';
    setChips([]);
    sendBtn.disabled = true;
    try {
      const r = await API.chat(currentUserId(), msg, sessionId);
      sessionId = r.session_id;
      addBubble('agent', renderMarkdown(r.advice), r.triage_level);
      setChips(r.followups || []);
      if (voiceOut.checked) Speech.speak(r.title + '。' + r.advice);
      if (r.suggest_120) toast('已建议拨打 120，请尽快处理', 'err');
      if (r.notified_guardian) toast('已通知监护人', 'info');
      loadDue();
    } catch (e) {
      addBubble('agent', '出错了：' + esc(e.message));
      toast('发送失败：' + e.message, 'err');
    } finally {
      sendBtn.disabled = false;
    }
  }

  sendBtn.onclick = send;
  input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

  micBtn.onclick = () => {
    if (recognizing) { recognizing = false; return; }
    recognizing = true;
    micBtn.style.background = '#dc2626';
    micBtn.style.color = '#fff';
    addBubble('agent', '🎤 我在听，请说话…');
    Speech.startRecognition((txt) => {
      input.value = txt;
    }, () => {
      recognizing = false;
      micBtn.style.background = '';
      micBtn.style.color = '';
      if (input.value.trim()) send();
    });
  };

  sosBtn.onclick = async () => {
    if (!confirm('确定要紧急呼救吗？将立即通知监护人与紧急联系人。')) return;
    try {
      const r = await API.sos(currentUserId());
      toast('紧急呼救已发出', 'err');
      Speech.speak('已为您发出紧急呼救，请保持电话畅通。');
    } catch (e) { toast('呼救失败：' + e.message, 'err'); }
  };

  async function loadDue() {
    try {
      const r = await API.reminders(currentUserId());
      const due = r.reminders.filter(x => x.due_now);
      if (!due.length) { dueList.textContent = '今日暂无待办提醒。'; return; }
      dueList.innerHTML = due.map(d => `
        <div class="alert-item info" style="margin-bottom:8px">
          <div><div class="title">${esc(d.title)}</div><div class="msg">${esc(d.detail || '')} · ${esc(d.cron)}</div></div>
          <button class="btn green small" onclick="window._take('${d.id}')">已完成</button>
        </div>`).join('');
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

  // 初始问候
  addBubble('agent', '您好，我是健康小助手。您哪里不舒服，可以直接告诉我，也可以点下面的🎤说话。');
  setChips(['我膝盖疼，一走路就痛', '我有点头晕', '我发烧了，浑身发冷', '我胸痛、胸闷']);
  if (voiceOut.checked) Speech.speak('您好，我是健康小助手。您哪里不舒服，可以直接告诉我。');
  API.seed(false).then(() => loadDue()).catch(() => loadDue());
})();
