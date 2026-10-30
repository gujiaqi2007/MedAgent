/* 监护人看板（含日程管理） */
(function () {
  if (!requireLogin()) return;
  const userSelect = document.getElementById('user-select');
  const latestBox = document.getElementById('latest-metrics');
  const dueList = document.getElementById('due-list');
  const alertList = document.getElementById('alert-list');
  const unreadBadge = document.getElementById('unread-badge');
  const chartsEl = document.getElementById('charts');
  const genWeekly = document.getElementById('gen-weekly');
  const reportCard = document.getElementById('report-card');
  const reportBody = document.getElementById('report-body');
  const schList = document.getElementById('schedule-list');
  const schTitle = document.getElementById('sch-title');
  const schDetail = document.getElementById('sch-detail');
  const schCron = document.getElementById('sch-cron');
  const schKind = document.getElementById('sch-kind');
  const schSave = document.getElementById('sch-save');
  const schCancel = document.getElementById('sch-cancel');
  const insightsEl = document.getElementById('insights');
  const careTaskList = document.getElementById('care-task-list');

  let editingId = null;
  let allReminders = [];

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
    const uid = currentUserId();
    const d = await API.guardianDashboard(uid);

    latestBox.innerHTML = d.latest.map(m => {
      const cls = m.flag ? (m.flag === 'high' ? 'high' : 'low') : '';
      return `<div class="metric ${cls}"><div class="label">${esc(m.label)}</div>
        <div class="value">${m.value}</div><div class="unit">${esc(m.unit)}</div></div>`;
    }).join('') || '<div class="muted small">暂无指标</div>';

    dueList.innerHTML = d.due_reminders.length
      ? d.due_reminders.map(x => `<div style="margin-bottom:6px">🔔 ${esc(x.title)}（${esc(x.cron)}）</div>`).join('')
      : '今日暂无待办。';

    unreadBadge.textContent = d.unread ? d.unread + ' 条未读' : '';
    unreadBadge.style.display = d.unread ? 'inline-block' : 'none';
    alertList.innerHTML = d.alerts.length
      ? d.alerts.slice(0, 12).map(a => `<div class="alert-item ${esc(a.severity)}">
          <div><div class="t">${esc(a.title)}</div><div class="m">${esc(a.message)}</div>
          <div class="muted small">${esc(a.created_at)} · ${a.status === 'acknowledged' ? '已确认' : '待确认'}</div></div>
          ${a.status === 'pending' ? `<button class="btn ghost sm" onclick="window._ack('${a.id}')">确认</button>` : ''}
        </div>`).join('')
      : '<div class="muted small">暂无告警。</div>';

    const keys = Object.keys(d.series || {});
    chartsEl.innerHTML = keys.map(t => `<div class="chart" data-metric="${t}"></div>`).join('') || '<div class="muted small">暂无数据</div>';
    chartsEl.querySelectorAll('.chart').forEach(el => {
      const t = el.dataset.metric, ref = REFS[t] || {};
      renderLineChart(el, d.series[t], { label: ref.label, unit: ref.unit, referenceLow: ref.low, referenceHigh: ref.high });
    });

    await loadSchedule(uid);
    await loadExtras(uid);
  }
  window._ack = async (id) => { await API.ackAlert(id); toast('已确认', 'ok'); refresh(); };

  async function loadExtras(uid) {
    try {
      const ai = await API.get('/api/anomaly-insights?user_id=' + uid);
      insightsEl.innerHTML = ai.insights.length
        ? ai.insights.map(x => `<div class="alert-item ${x.direction === 'high' ? 'red' : 'yellow'}" style="margin-bottom:8px">
            <div><div class="t">${esc(x.label)} ${x.value} ${esc(x.unit)}（参考 ${esc(x.reference)}）</div>
            <div class="m">可能原因：${esc(x.cause)}</div>
            <div class="m">现在该做：${esc(x.action)}</div></div></div>`).join('')
        : '<div class="muted small">各项指标均在参考范围内。</div>';
    } catch (e) { insightsEl.textContent = '加载失败'; }
    try {
      const ct = await API.get('/api/care-tasks?user_id=' + uid);
      const todo = ct.tasks.filter(t => t.status !== 'done');
      const done = ct.tasks.filter(t => t.status === 'done');
      careTaskList.innerHTML = (todo.length
        ? todo.map(t => `<div class="alert-item info" style="margin-bottom:8px">
            <div><div class="t">${esc(t.title)}</div><div class="m">${esc(t.detail || '')}${t.assignee ? ' · ' + esc(t.assignee) : ''}</div></div>
            <div class="row" style="flex-wrap:nowrap">
              <button class="btn green sm" onclick="window._doneTask('${t.id}')">完成</button>
              <button class="btn ghost sm" onclick="window._delTask('${t.id}')">删除</button>
            </div></div>`).join('')
        : '<div class="muted small">暂无待办任务。</div>')
        + (done.length ? `<div class="muted small" style="margin-top:6px">已完成 ${done.length} 项</div>` : '');
    } catch (e) { careTaskList.textContent = '加载失败'; }
  }
  window._doneTask = async (id) => { await API.post('/api/care-tasks/' + id + '/done'); toast('已完成', 'ok'); loadExtras(currentUserId()); };
  window._delTask = async (id) => { await API.del('/api/care-tasks/' + id); toast('已删除', 'ok'); loadExtras(currentUserId()); };

  document.getElementById('g-save-metric').onclick = async () => {
    const type = document.getElementById('g-metric-type').value;
    const value = parseFloat(document.getElementById('g-metric-value').value);
    if (isNaN(value)) { toast('请输入数值', 'warn'); return; }
    try {
      await API.addMetric({ user_id: currentUserId(), metrics: [{ type, value, source: 'manual' }] });
      document.getElementById('g-metric-value').value = '';
      toast('已代录', 'ok');
      refresh();
    } catch (e) { toast('代录失败：' + e.message, 'err'); }
  };

  document.getElementById('task-add').onclick = async () => {
    const title = document.getElementById('task-title').value.trim();
    if (!title) { toast('请填写任务', 'warn'); return; }
    try {
      await API.post('/api/care-tasks', {
        user_id: currentUserId(), title,
        detail: document.getElementById('task-detail').value.trim(),
        assignee: localStorage.getItem('medagent_name') || '',
      });
      toast('已添加', 'ok');
      document.getElementById('task-title').value = '';
      document.getElementById('task-detail').value = '';
      loadExtras(currentUserId());
    } catch (e) { toast('添加失败：' + e.message, 'err'); }
  };

  document.getElementById('bind-btn').onclick = async () => {
    const uid = document.getElementById('bind-user-id').value.trim();
    if (!uid) return;
    try {
      await API.bind(uid);
      toast('绑定成功', 'ok');
      await loadUsers();
      refresh();
    } catch (e) { toast('绑定失败：' + e.message, 'err'); }
  };

  async function loadSchedule(uid) {
    const r = await API.reminders(uid);
    allReminders = r.reminders;
    schList.innerHTML = allReminders.length
      ? allReminders.map(x => `<div class="alert-item info" style="margin-bottom:8px">
          <div><div class="t">${esc(x.title)}</div><div class="m">${esc(x.detail || '')} · 每天 ${esc(x.cron)} · ${x.enabled ? '启用' : '停用'}</div></div>
          <div class="row" style="flex-wrap:nowrap">
            <button class="btn ghost sm" onclick="window._edit('${x.id}')">编辑</button>
            <button class="btn ghost sm" onclick="window._del('${x.id}')">删除</button>
          </div></div>`).join('')
      : '<div class="muted small">暂无日程，请在下方新增。</div>';
  }
  window._edit = (id) => {
    const r = allReminders.find(x => x.id === id);
    if (!r) return;
    editingId = id;
    schTitle.value = r.title; schDetail.value = r.detail || '';
    schCron.value = r.cron; schKind.value = r.kind || 'medication';
    schSave.textContent = '保存修改';
    schCancel.style.display = '';
    schTitle.focus();
  };
  window._del = async (id) => {
    if (!confirm('确定删除这条日程吗？')) return;
    await API.deleteReminder(id);
    toast('已删除', 'ok');
    loadSchedule(currentUserId());
  };
  schCancel.onclick = () => {
    editingId = null; schTitle.value = ''; schDetail.value = ''; schCron.value = '08:00';
    schSave.textContent = '保存日程'; schCancel.style.display = 'none';
  };
  schSave.onclick = async () => {
    const payload = {
      user_id: currentUserId(), kind: schKind.value, title: schTitle.value.trim(),
      detail: schDetail.value.trim(), cron: schCron.value.trim() || '08:00',
    };
    if (!payload.title) { toast('请填写标题', 'warn'); return; }
    try {
      if (editingId) await API.updateReminder(editingId, payload);
      else await API.createReminder(payload);
      toast(editingId ? '已保存修改' : '已新增日程', 'ok');
      schCancel.onclick();
      loadSchedule(currentUserId());
    } catch (e) { toast('保存失败：' + e.message, 'err'); }
  };

  genWeekly.onclick = async () => {
    try {
      const r = await API.weekly(currentUserId());
      const rep = r.report;
      reportBody.innerHTML = `
        <h3>${esc(rep.summary.label)}（${esc(rep.summary.period_start.slice(0, 10))} 至 ${esc(rep.summary.period_end.slice(0, 10))}）</h3>
        <p class="muted small">指标 ${rep.summary.metric_count} 项 · 异常 ${rep.summary.anomaly_count} 项</p>
        ${rep.anomalies.length ? `<h3>⚠️ 异常提醒</h3><table><tr><th>指标</th><th>最新值</th><th>参考区间</th></tr>
          ${rep.anomalies.map(a => `<tr><td>${esc(a.label)}</td><td><b style="color:#dc2626">${a.latest} ${esc(a.unit)}</b></td><td>${esc(a.reference)}</td></tr>`).join('')}</table>` : '<p class="small">未发现异常指标。</p>'}
        <h3>指标明细</h3>
        <table><tr><th>指标</th><th>最新</th><th>均值</th><th>范围</th><th>趋势</th></tr>
          ${Object.keys(rep.summary.metrics).map(t => { const m = rep.summary.metrics[t];
            const tr = m.trend === '上升' ? '↑ 上升' : m.trend === '下降' ? '↓ 下降' : '→ 平稳';
            return `<tr><td>${esc(m.label)}</td><td><b>${m.latest}</b> ${esc(m.unit)}</td><td>${m.avg}</td><td>${m.min}–${m.max}</td><td>${tr}</td></tr>`; }).join('')}</table>
        <h3>💡 生活建议</h3><ul>${rep.advice.map(a => `<li>${esc(a)}</li>`).join('')}</ul>`;
      reportCard.style.display = 'block';
      reportCard.scrollIntoView({ behavior: 'smooth' });
    } catch (e) { toast('生成报告失败：' + e.message, 'err'); }
  };

  (async function init() {
    try { await loadMe(); } catch (e) {}
    const role = localStorage.getItem('medagent_role') || 'guardian';
    renderSidebar(role, 'guardian');
    try { await loadUsers(); } catch (e) { toast('加载用户失败：' + e.message, 'err'); }
    refresh().catch(e => toast('加载失败：' + e.message, 'err'));
    setInterval(() => refresh().catch(() => {}), 20000);
  })();
})();
