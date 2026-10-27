/* 监护人模式逻辑 */
(function () {
  const userSelect = document.getElementById('user-select');
  const latestBox = document.getElementById('latest-metrics');
  const dueList = document.getElementById('due-list');
  const alertList = document.getElementById('alert-list');
  const unreadBadge = document.getElementById('unread-badge');
  const chartsEl = document.getElementById('charts');
  const genWeekly = document.getElementById('gen-weekly');
  const reportCard = document.getElementById('report-card');
  const reportBody = document.getElementById('report-body');

  const REFS = {
    heart_rate: { label: '心率', unit: '次/分', low: 60, high: 100 },
    blood_pressure_sys: { label: '收缩压', unit: 'mmHg', low: 90, high: 140 },
    blood_pressure_dia: { label: '舒张压', unit: 'mmHg', low: 60, high: 90 },
    blood_oxygen: { label: '血氧', unit: '%', low: 95, high: 100 },
    blood_glucose: { label: '血糖', unit: 'mmol/L', low: 3.9, high: 6.1 },
    sleep_hours: { label: '睡眠', unit: '小时', low: 6, high: 9 },
    steps: { label: '步数', unit: '步', low: 3000, high: 20000 },
    weight: { label: '体重', unit: 'kg', low: 40, high: 90 },
    temperature: { label: '体温', unit: '℃', low: 36, high: 37.3 },
  };

  async function loadUsers() {
    const r = await API.users();
    userSelect.innerHTML = r.users.map(u =>
      `<option value="${u.id}" ${u.id === currentUserId() ? 'selected' : ''}>${esc(u.name)}</option>`).join('');
  }
  userSelect.onchange = () => setCurrentUserId(userSelect.value);

  async function refresh() {
    const uid = currentUserId();
    const d = await API.guardianDashboard(uid);

    // 指标卡片
    latestBox.innerHTML = d.latest.map(m => {
      const cls = m.flag ? ` flag-${m.flag === 'high' ? 'high' : 'low'}` : '';
      return `<div class="metric${cls}"><div class="label">${esc(m.label)}</div>
        <div class="value">${m.value}</div><div class="unit">${esc(m.unit)}</div></div>`;
    }).join('') || '<div class="muted small">暂无指标数据</div>';

    // 待办
    dueList.innerHTML = d.due_reminders.length
      ? d.due_reminders.map(x => `<div class="small" style="margin-bottom:6px">🔔 ${esc(x.title)}（${esc(x.cron)}）</div>`).join('')
      : '今日暂无待办。';

    // 告警
    unreadBadge.textContent = d.unread ? d.unread + ' 条未读' : '';
    unreadBadge.style.display = d.unread ? 'inline-block' : 'none';
    alertList.innerHTML = d.alerts.length
      ? d.alerts.slice(0, 15).map(a => `
        <div class="alert-item ${esc(a.severity)}">
          <div>
            <div class="title">${esc(a.title)}</div>
            <div class="msg">${esc(a.message)}</div>
            <div class="muted small">${esc(a.created_at)} · ${a.status === 'acknowledged' ? '已确认' : '待确认'}</div>
          </div>
          ${a.status === 'pending' ? `<button class="btn ghost small" onclick="window._ack('${a.id}')">确认</button>` : ''}
        </div>`).join('')
      : '<div class="muted small">暂无告警。</div>';

    // 图表
    const keys = Object.keys(d.series || {});
    chartsEl.innerHTML = keys.map(t => {
      const ref = REFS[t] || {};
      const div = document.createElement('div');
      div.className = 'chart';
      return `<div class="chart" data-metric="${t}"></div>`;
    }).join('') || '<div class="muted small">暂无趋势数据。</div>';
    chartsEl.querySelectorAll('.chart').forEach(el => {
      const t = el.dataset.metric;
      const ref = REFS[t] || {};
      renderLineChart(el, d.series[t], { label: ref.label, unit: ref.unit, referenceLow: ref.low, referenceHigh: ref.high });
    });
  }
  window._ack = async (id) => {
    await API.ackAlert(id);
    toast('已确认', 'ok');
    refresh();
  };

  genWeekly.onclick = async () => {
    try {
      const r = await API.weekly(currentUserId());
      const rep = r.report;
      reportBody.innerHTML = `
        <h3>${esc(rep.summary.label)}（${esc(rep.summary.period_start.slice(0,10))} 至 ${esc(rep.summary.period_end.slice(0,10))}）</h3>
        <p class="muted small">指标 ${rep.summary.metric_count} 项 · 异常 ${rep.summary.anomaly_count} 项</p>
        ${rep.anomalies.length ? `<h3>⚠️ 异常提醒</h3><table><tr><th>指标</th><th>最新值</th><th>参考区间</th></tr>
          ${rep.anomalies.map(a => `<tr><td>${esc(a.label)}</td><td><b style="color:#dc2626">${a.latest} ${esc(a.unit)}</b></td><td>${esc(a.reference)}</td></tr>`).join('')}</table>` : '<p class="small">未发现异常指标。</p>'}
        <h3>📋 指标明细</h3>
        <table><tr><th>指标</th><th>最新</th><th>均值</th><th>范围</th><th>趋势</th></tr>
          ${renderTrendRows(rep.summary.metrics)}</table>
        <h3>💡 生活建议</h3><ul>${rep.advice.map(a => `<li>${esc(a)}</li>`).join('')}</ul>`;
      reportCard.style.display = 'block';
      reportCard.scrollIntoView({ behavior: 'smooth' });
    } catch (e) { toast('生成报告失败：' + e.message, 'err'); }
  };

  function renderTrendRows(metricsMap) {
    return Object.keys(metricsMap || {}).map(t => {
      const m = metricsMap[t];
      const trend = m.trend === '上升' ? '↑ 上升' : m.trend === '下降' ? '↓ 下降' : '→ 平稳';
      return `<tr><td>${esc(m.label)}</td><td><b>${m.latest}</b> ${esc(m.unit)}</td><td>${m.avg}</td><td>${m.min}–${m.max}</td><td>${trend}</td></tr>`;
    }).join('');
  }

  // 轮询刷新（每 20 秒）
  (async function init() {
    try { await API.seed(false); await loadUsers(); } catch (e) { toast('加载用户失败：' + e.message, 'err'); }
    refresh().catch(e => toast('加载失败：' + e.message, 'err'));
    setInterval(() => refresh().catch(() => {}), 20000);
  })();
})();
