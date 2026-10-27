/* MedAgent 前端 API 封装 */
const API = {
  base: '',

  async _req(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(API.base + path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || ('HTTP ' + res.status));
    }
    return data;
  },

  get(path) { return this._req('GET', path); },
  post(path, body) { return this._req('POST', path, body); },
  put(path, body) { return this._req('PUT', path, body); },

  // 便捷方法
  seed(force) { return this.post('/api/seed', { force: !!force }); },
  chat(userId, message, sessionId) { return this.post('/api/chat', { user_id: userId, message, session_id: sessionId }); },
  sos(userId) { return this.post('/api/sos', { user_id: userId }); },
  metrics(userId, type, limit) {
    const q = new URLSearchParams({ user_id: userId });
    if (type) q.set('type', type);
    if (limit) q.set('limit', limit);
    return this.get('/api/metrics?' + q);
  },
  addMetric(payload) { return this.post('/api/metrics', payload); },
  alerts(userId) { return this.get('/api/alerts?user_id=' + userId); },
  ackAlert(id) { return this.post('/api/alerts/' + id + '/ack'); },
  reminders(userId) { return this.get('/api/reminders?user_id=' + userId); },
  createReminder(payload) { return this.post('/api/reminders', payload); },
  takeReminder(id, userId) { return this.post('/api/reminders/' + id + '/take', { user_id: userId }); },
  weekly(userId) { return this.get('/api/reports/weekly?user_id=' + userId); },
  monthly(userId) { return this.get('/api/reports/monthly?user_id=' + userId); },
  exportReport(type, userId) { return this.get('/api/reports/' + type + '/export?user_id=' + userId); },
  guardianDashboard(userId) { return this.get('/api/guardian/dashboard?user_id=' + userId); },
  doctorOverview(userId) { return this.get('/api/doctor/overview?user_id=' + userId); },
  users() { return this.get('/api/users'); },
  user(id) { return this.get('/api/users/' + id); },
};

// 默认演示使用者
const DEMO_USER_ID = 'u_demo_zhang';
function currentUserId() {
  return localStorage.getItem('medagent_user_id') || DEMO_USER_ID;
}
function setCurrentUserId(id) {
  localStorage.setItem('medagent_user_id', id);
}
