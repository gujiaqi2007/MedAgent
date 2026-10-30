/* 医生工作台（含开具医嘱） */
(function () {
  if (!requireLogin()) return;
  const userSelect = document.getElementById('user-select');
  const patientInfo = document.getElementById('patient-info');
  const reportBody = document.getElementById('report-body');
  const chartsEl = document.getElementById('charts');
  const exportBtn = document.getElementById('export-btn');
  const orderList = document.getElementById('order-list');
  const ordTitle = document.getElementById('ord-title');
  const ordMed = document.getElementById('ord-med');
  const ordDosage = document.getElementById('ord-dosage');
  const ordFreq = document.getElementById('ord-freq');
  const ordDays = document.getElementById('ord-days');
  const ordCron = document.getElementById('ord-cron');
  const ordNote = document.getElementById('ord-note');
  const ordSave = document.getElementById('ord-save');
  const patientListEl = document.getElementById('patient-list');
  const followupListEl = document.getElementById('followup-list');
  const consultListEl = document.getElementById('consult-list');
  const consultDetailEl = document.getElementById('consult-detail');

  const REFS = {
    heart_rate: { label: '心率', unit: '次/分', low: 60, high: 100 },
    blood_pressure_sys: { label: '收缩压', unit: 'mmHg', low: 90, high: 140 },
    blood_pressure_dia: { label: '舒张压', unit: 'mmHg', low: 60, high: 90 },
    blood_oxygen: { label: '血氧', unit: '%', low: 95, high: 100 },
    blood_glucose: { label: '血糖', unit: 'mmol/L', low: 3.9, high: 6.1 },
    sleep_hours: { label: '睡眠', unit: '小时', low: 6, high: 9 },
    steps: { label: '步数', unit: '步', low: 3000, high: 20000 },
    weight: { label: '体重', unit: 'kg', low: 40, high: 90 },
  };

  async function loadUsers() {
    const r = await API.users();
    const list = r.users.filter(u => u.bound).length ? r.users.filter(u => u.bound) : r.users;
    userSelect.innerHTML = list.map(u =>
      `<option value="${u.id}" ${u.id === currentUserId() ? 'selected' : ''}>${esc(u.name)}</option>`).join('');
    if (!list.some(u => u.id === currentUserId()) && list.length) setCurrentUserId(list[0].id);
  }
  userSelect.onchange = () => { setCurrentUserId(userSelect.value); refresh(); };

  async function refresh() {
    const d = await API.doctorOverview(currentUserId());
    const u = d.user || {};
    patientInfo.innerHTML = `
      <p style="margin:4px 0"><b>姓名：</b>${esc(u.name)} · ${esc(u.gender || '')} · ${esc(u.birth_date || '')}</p>
      <p style="margin:4px 0"><b>既往病史：</b>${(u.medical_history || []).map(esc).join('、') || '无'}</p>
      <p style="margin:4px 0"><b>过敏史：</b>${(u.allergies || []).map(esc).join('、') || '无'}</p>
      <p style="margin:4px 0"><b>当前用药：</b>${(u.current_medications || []).map(esc).join('、') || '无'}</p>`;

    orderList.innerHTML = d.orders.length
      ? d.orders.map(o => `<div class="alert-item info" style="margin-bottom:8px">
          <div><div class="t">${esc(o.title)}</div>
          <div class="m">${esc([o.medication, o.dosage, o.frequency].filter(Boolean).join(' · '))}${o.instructions ? ' — ' + esc(o.instructions) : ''}</div>
          <div class="muted small">${esc(o.created_at)} · ${o.status === 'active' ? '执行中' : '已停止'}</div></div>
          ${o.status === 'active' ? `<button class="btn ghost sm" onclick="window._stop('${o.id}')">停止</button>` : ''}
        </div>`).join('')
      : '<div class="muted small">暂无医嘱。</div>';

    const rep = d.weekly.summary;
    reportBody.innerHTML = `
      <p class="muted small">${esc(rep.period_start.slice(0, 10))} 至 ${esc(rep.period_end.slice(0, 10))} · 指标 ${rep.metric_count} 项 · 异常 ${rep.anomaly_count} 项</p>
      ${d.weekly.anomalies.length ? `<table><tr><th>指标</th><th>最新值</th><th>参考</th></tr>
        ${d.weekly.anomalies.map(a => `<tr><td>${esc(a.label)}</td><td><b style="color:#dc2626">${a.latest} ${esc(a.unit)}</b></td><td>${esc(a.reference)}</td></tr>`).join('')}</table>` : '<p class="small">未发现异常。</p>'}
      <h3>生活建议</h3><ul class="small">${d.weekly.advice.map(a => `<li>${esc(a)}</li>`).join('')}</ul>
      <p class="muted small">居家监测数据，供医生参考，不构成诊断。</p>`;

    const keys = Object.keys(d.series || {});
    chartsEl.innerHTML = keys.map(t => `<div class="chart" data-metric="${t}"></div>`).join('') || '<div class="muted small">暂无数据</div>';
    chartsEl.querySelectorAll('.chart').forEach(el => {
      const t = el.dataset.metric, ref = REFS[t] || {};
      renderLineChart(el, d.series[t], { label: ref.label, unit: ref.unit, referenceLow: ref.low, referenceHigh: ref.high });
    });
    await loadPatientList();
    await loadFollowups();
    await loadConsultations();
  }

  async function loadPatientList() {
    try {
      const r = await API.get('/api/patients');
      patientListEl.innerHTML = r.patients.length
        ? r.patients.map(p => `<div class="alert-item ${p.anomalies > 0 ? 'red' : 'info'}" style="margin-bottom:8px">
            <div><div class="t">${esc(p.name)} ${p.bound ? '<span class="badge blue">已绑定</span>' : '<span class="badge gray">未绑定</span>'}</div>
            <div class="m">${(p.medical_history || []).map(esc).join('、') || '无病史'} · 异常 ${p.anomalies} 项</div></div>
            <button class="btn ghost sm" onclick="window._pickPatient('${p.user_id}')">查看</button></div>`).join('')
        : '<div class="muted small">暂无患者。</div>';
    } catch (e) { patientListEl.textContent = '加载失败'; }
  }
  window._pickPatient = (id) => { setCurrentUserId(id); refresh(); };

  async function loadFollowups() {
    try {
      const r = await API.get('/api/followups?user_id=' + currentUserId());
      followupListEl.innerHTML = r.followups.length
        ? r.followups.map(f => `<div class="alert-item info" style="margin-bottom:8px">
            <div><div class="t">${esc(f.title)}</div><div class="m">${esc(f.plan || '')}${f.next_date ? ' · 下次 ' + esc(f.next_date) : ''}</div></div>
            ${f.status === 'active' ? `<button class="btn ghost sm" onclick="window._doneFu('${f.id}')">完成</button>` : '<span class="badge gray">已完成</span>'}</div>`).join('')
        : '<div class="muted small">暂无随访计划。</div>';
    } catch (e) { followupListEl.textContent = '加载失败'; }
  }
  window._doneFu = async (id) => { await API.put('/api/followups/' + id, { status: 'done' }); toast('随访已完成', 'ok'); loadFollowups(); };

  async function loadConsultations() {
    try {
      const r = await API.get('/api/consultations?user_id=' + currentUserId());
      consultListEl.innerHTML = r.consultations.length
        ? r.consultations.map(c => `<div class="alert-item info" style="margin-bottom:8px">
            <div><div class="t">${esc(c.subject)}</div><div class="m">${c.status === 'replied' ? '已回复' : c.status === 'closed' ? '已关闭' : '待回复'} · ${esc(c.created_at)}</div></div>
            <button class="btn ghost sm" onclick="window._openConsult('${c.id}')">查看</button></div>`).join('')
        : '<div class="muted small">暂无问诊。</div>';
    } catch (e) { consultListEl.textContent = '加载失败'; }
  }
  window._openConsult = async (id) => {
    const r = await API.get('/api/consultations/' + id);
    consultDetailEl.innerHTML = `
      <h3>${esc(r.consultation.subject)}</h3>
      <div class="chat-box" style="height:200px;overflow:auto">
        ${r.messages.map(m => `<div class="msg ${m.role === 'doctor' ? 'ai' : 'me'}"><div class="avatar">${m.role === 'doctor' ? '🩺' : '🙂'}</div><div class="bubble">${esc(m.text)}</div></div>`).join('')}
      </div>
      <div class="chat-input">
        <input id="cd-input" placeholder="回复患者…">
        <button class="btn primary" onclick="window._reply('${id}')">发送</button>
      </div>`;
  };
  window._reply = async (id) => {
    const text = document.getElementById('cd-input').value.trim();
    if (!text) return;
    await API.post('/api/consultations/' + id + '/messages', { text });
    toast('已回复', 'ok');
    window._openConsult(id);
    loadConsultations();
  };
  window._stop = async (id) => { await API.stopOrder(id); toast('医嘱已停止', 'ok'); refresh(); };

  ordSave.onclick = async () => {
    const title = ordTitle.value.trim();
    if (!title) { toast('请填写医嘱标题', 'warn'); return; }
    try {
      await API.createOrder({
        user_id: currentUserId(), title,
        medication: ordMed.value.trim(), dosage: ordDosage.value.trim(),
        frequency: ordFreq.value.trim(), duration_days: Number(ordDays.value) || null,
        instructions: ordNote.value.trim(), cron: ordCron.value.trim() || '08:00',
      });
      toast('医嘱已开具，并已加入每日提醒', 'ok');
      ordTitle.value = ordMed.value = ordDosage.value = ordFreq.value = ordDays.value = ordNote.value = '';
      refresh();
    } catch (e) { toast('开具失败：' + e.message, 'err'); }
  };

  document.getElementById('fu-add').onclick = async () => {
    const title = document.getElementById('fu-title').value.trim();
    if (!title) { toast('请填写随访主题', 'warn'); return; }
    try {
      await API.post('/api/followups', {
        user_id: currentUserId(), title,
        next_date: document.getElementById('fu-date').value || null,
      });
      toast('已创建随访', 'ok');
      document.getElementById('fu-title').value = '';
      loadFollowups();
    } catch (e) { toast('创建失败：' + e.message, 'err'); }
  };

  document.getElementById('sign-btn').onclick = async () => {
    try {
      await API.post('/api/signings', { user_id: currentUserId() });
      toast('已签约家庭医生', 'ok');
    } catch (e) { toast('签约失败：' + e.message, 'err'); }
  };

  exportBtn.onclick = async () => {
    try {
      const r = await API.exportReport('weekly', currentUserId());
      const blob = new Blob([JSON.stringify(r.export, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `medagent_${currentUserId()}_${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast('已导出诊断凭据', 'ok');
    } catch (e) { toast('导出失败：' + e.message, 'err'); }
  };

  (async function init() {
    try { await loadMe(); } catch (e) {}
    const role = localStorage.getItem('medagent_role') || 'doctor';
    renderSidebar(role, 'doctor');
    try { await loadUsers(); } catch (e) { toast('加载用户失败：' + e.message, 'err'); }
    refresh().catch(e => toast('加载失败：' + e.message, 'err'));
  })();
})();
