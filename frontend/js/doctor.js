/* 医生模式逻辑 */
(function () {
  const userSelect = document.getElementById('user-select');
  const patientInfo = document.getElementById('patient-info');
  const reportBody = document.getElementById('report-body');
  const chartsEl = document.getElementById('charts');
  const exportBtn = document.getElementById('export-btn');

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
    userSelect.innerHTML = r.users.map(u =>
      `<option value="${u.id}" ${u.id === currentUserId() ? 'selected' : ''}>${esc(u.name)}</option>`).join('');
  }
  userSelect.onchange = () => setCurrentUserId(userSelect.value);

  async function refresh() {
    const uid = currentUserId();
    const d = await API.doctorOverview(uid);
    const u = d.user || {};

    patientInfo.innerHTML = `
      <p style="margin:4px 0"><b>姓名：</b>${esc(u.name)} · ${esc(u.gender || '')} · ${esc(u.birth_date || '')}</p>
      <p style="margin:4px 0"><b>既往病史：</b>${(u.medical_history || []).map(esc).join('、') || '无'}</p>
      <p style="margin:4px 0"><b>过敏史：</b>${(u.allergies || []).map(esc).join('、') || '无'}</p>
      <p style="margin:4px 0"><b>当前用药：</b>${(u.current_medications || []).map(esc).join('、') || '无'}</p>`;

    const rep = d.weekly.summary;
    reportBody.innerHTML = `
      <p class="muted small">统计周期 ${esc(rep.period_start.slice(0,10))} 至 ${esc(rep.period_end.slice(0,10))} · 指标 ${rep.metric_count} 项 · 异常 ${rep.anomaly_count} 项</p>
      ${d.weekly.anomalies.length ? `<h3>⚠️ 异常指标</h3><table><tr><th>指标</th><th>最新值</th><th>参考区间</th><th>方向</th></tr>
        ${d.weekly.anomalies.map(a => `<tr><td>${esc(a.label)}</td><td><b style="color:#dc2626">${a.latest} ${esc(a.unit)}</b></td><td>${esc(a.reference)}</td><td>${a.direction === 'high' ? '偏高' : '偏低'}</td></tr>`).join('')}</table>` : '<p class="small">未发现异常。</p>'}
      <h3>指标明细</h3>
      <table><tr><th>指标</th><th>最新</th><th>均值</th><th>范围</th><th>趋势</th></tr>
        ${Object.keys(rep.metrics).map(t => { const m = rep.metrics[t];
          const tr = m.trend === '上升' ? '↑ 上升' : m.trend === '下降' ? '↓ 下降' : '→ 平稳';
          return `<tr><td>${esc(m.label)}</td><td><b>${m.latest}</b> ${esc(m.unit)}</td><td>${m.avg}</td><td>${m.min}–${m.max}</td><td>${tr}</td></tr>`; }).join('')}</table>
      <h3>💡 生活建议</h3><ul>${d.weekly.advice.map(a => `<li>${esc(a)}</li>`).join('')}</ul>
      <p class="muted small">本数据为居家健康监测记录，供医生参考，不构成诊断。</p>`;

    const keys = Object.keys(d.series || {});
    chartsEl.innerHTML = keys.map(t => `<div class="chart" data-metric="${t}"></div>`).join('') || '<div class="muted small">暂无数据</div>';
    chartsEl.querySelectorAll('.chart').forEach(el => {
      const t = el.dataset.metric;
      const ref = REFS[t] || {};
      renderLineChart(el, d.series[t], { label: ref.label, unit: ref.unit, referenceLow: ref.low, referenceHigh: ref.high });
    });
  }

  exportBtn.onclick = async () => {
    try {
      const r = await API.exportReport('weekly', currentUserId());
      const blob = new Blob([JSON.stringify(r.export, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `medagent_report_${currentUserId()}_${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast('已导出诊断凭据（JSON）', 'ok');
    } catch (e) { toast('导出失败：' + e.message, 'err'); }
  };

  (async function init() {
    try { await API.seed(false); await loadUsers(); } catch (e) { toast('加载用户失败：' + e.message, 'err'); }
    refresh().catch(e => toast('加载失败：' + e.message, 'err'));
  })();
})();
