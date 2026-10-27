/* 轻量 SVG 折线图（无外部依赖，离线可用） */
function renderLineChart(el, series, opts) {
  opts = opts || {};
  const label = opts.label || '';
  const unit = opts.unit || '';
  const refLow = opts.referenceLow;
  const refHigh = opts.referenceHigh;

  if (!series || series.length === 0) {
    el.innerHTML = '<div class="muted small" style="padding:14px">暂无数据</div>';
    return;
  }

  const W = el.clientWidth || 600;
  const H = 180;
  const pad = { l: 40, r: 12, t: 26, b: 26 };

  const values = series.map(d => Number(d.value));
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (refLow !== undefined && refLow !== null) lo = Math.min(lo, refLow);
  if (refHigh !== undefined && refHigh !== null) hi = Math.max(hi, refHigh);
  const span = (hi - lo) || 1;
  lo -= span * 0.12; hi += span * 0.12;

  const x = i => pad.l + (W - pad.l - pad.r) * (series.length === 1 ? 0.5 : i / (series.length - 1));
  const y = v => pad.t + (H - pad.t - pad.b) * (1 - (v - lo) / (hi - lo));

  let pts = series.map((d, i) => `${x(i)},${y(Number(d.value))}`).join(' ');
  let refLowLine = refLow !== undefined && refLow !== null ? y(refLow) : null;
  let refHighLine = refHigh !== undefined && refHigh !== null ? y(refHigh) : null;

  const lastVal = Number(series[series.length - 1].value);
  const flag = (refHigh !== undefined && refHigh !== null && lastVal > refHigh) ? 'red'
    : (refLow !== undefined && refLow !== null && lastVal < refLow) ? 'orange' : 'blue';
  const color = flag === 'red' ? '#dc2626' : flag === 'orange' ? '#d97706' : '#2563eb';

  el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img">
      <text x="${pad.l}" y="14" font-size="13" fill="#1f2d3d" font-weight="600">${label}（近30天）</text>
      ${refHighLine !== null ? `<line x1="${pad.l}" x2="${W - pad.r}" y1="${refHighLine}" y2="${refHighLine}" stroke="#dc2626" stroke-dasharray="4 4" opacity=".5"/>` : ''}
      ${refLowLine !== null ? `<line x1="${pad.l}" x2="${W - pad.r}" y1="${refLowLine}" y2="${refLowLine}" stroke="#d97706" stroke-dasharray="4 4" opacity=".5"/>` : ''}
      <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"/>
      ${series.map((d, i) => `<circle cx="${x(i)}" cy="${y(Number(d.value))}" r="2.6" fill="${color}"/>`).join('')}
      <circle cx="${x(series.length - 1)}" cy="${y(lastVal)}" r="4.5" fill="${color}" opacity=".9"/>
      <text x="${W - pad.r}" y="${H - 8}" font-size="11" fill="#6b7a8d" text-anchor="end">最新 ${lastVal}${unit}</text>
    </svg>`;
}

function renderTrendList(el, metricsMap, refs) {
  const keys = Object.keys(metricsMap || {});
  if (!keys.length) { el.innerHTML = '<div class="muted small">暂无指标</div>'; return; }
  el.innerHTML = keys.map(t => {
    const m = metricsMap[t];
    const ref = refs[t] || {};
    const trend = m.trend === '上升' ? '↑ 上升' : m.trend === '下降' ? '↓ 下降' : '→ 平稳';
    const cls = m.trend === '上升' ? 'yellow' : m.trend === '下降' ? 'green' : 'gray';
    return `<tr><td>${m.label}</td><td><b>${m.latest}</b> ${m.unit}</td>
      <td>均值 ${m.avg}</td><td>${m.min}–${m.max}</td>
      <td><span class="badge ${cls}">${trend}</span></td></tr>`;
  }).join('');
}
