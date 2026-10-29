/* MedAgent 前端 API 封装（含登录令牌与新接口） */
const API = {
  base: '',

  token() { return localStorage.getItem('medagent_token') || ''; },
  setToken(t) { localStorage.setItem('medagent_token', t); },
  clearToken() { localStorage.removeItem('medagent_token'); },

  async _req(method, path, body) {
    const headers = { 'Content-Type': 'application/json' };
    const t = this.token();
    if (t) headers['Authorization'] = 'Bearer ' + t;
    const opts = { method, headers };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(this.base + path, opts);
    let data = {};
    try { data = await res.json(); } catch (e) {}
    if (res.status === 401) {
      this.clearToken();
      if (!location.pathname.startsWith('/login')) location.href = '/login';
      throw new Error('请先登录');
    }
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    return data;
  },

  get(path) { return this._req('GET', path); },
  post(path, body) { return this._req('POST', path, body); },
  put(path, body) { return this._req('PUT', path, body); },
  del(path) { return this._req('DELETE', path); },

  // 鉴权
  login(username, password) { return this.post('/api/auth/login', { username, password }); },
  register(username, password, role, display_name) { return this.post('/api/auth/register', { username, password, role, display_name }); },
  logout() { return this.post('/api/auth/logout', {}); },
  me() { return this.get('/api/auth/me'); },
  bind(userId) { return this.post('/api/bind', { user_id: userId }); },
  unbind(userId) { return this.post('/api/unbind', { user_id: userId }); },

  // 业务
  seed(force) { return this.post('/api/seed', { force: !!force }); },
  users() { return this.get('/api/users'); },
  user(id) { return this.get('/api/users/' + id); },
  chat(userId, message, sessionId) { return this.post('/api/chat', { user_id: userId, message, session_id: sessionId }); },
  sos(userId) { return this.post('/api/sos', { user_id: userId }); },
  addMetric(payload) { return this.post('/api/metrics', payload); },
  metrics(userId, type) { const q = new URLSearchParams({ user_id: userId }); if (type) q.set('type', type); return this.get('/api/metrics?' + q); },
  devices(userId) { return this.get('/api/devices?user_id=' + userId); },
  syncDevice(userId, simulate) { return this.post('/api/devices/sync', { user_id: userId, simulate: simulate !== false }); },
  alerts(userId) { return this.get('/api/alerts?user_id=' + userId); },
  ackAlert(id) { return this.post('/api/alerts/' + id + '/ack'); },
  reminders(userId) { return this.get('/api/reminders?user_id=' + userId); },
  createReminder(payload) { return this.post('/api/reminders', payload); },
  updateReminder(id, payload) { return this.put('/api/reminders/' + id, payload); },
  deleteReminder(id) { return this.del('/api/reminders/' + id); },
  takeReminder(id, userId) { return this.post('/api/reminders/' + id + '/take', { user_id: userId }); },
  orders(userId) { return this.get('/api/orders?user_id=' + userId); },
  createOrder(payload) { return this.post('/api/orders', payload); },
  stopOrder(id) { return this.post('/api/orders/' + id + '/stop'); },
  weekly(userId) { return this.get('/api/reports/weekly?user_id=' + userId); },
  monthly(userId) { return this.get('/api/reports/monthly?user_id=' + userId); },
  exportReport(type, userId) { return this.get('/api/reports/' + type + '/export?user_id=' + userId); },
  guardianDashboard(userId) { return this.get('/api/guardian/dashboard?user_id=' + userId); },
  doctorOverview(userId) { return this.get('/api/doctor/overview?user_id=' + userId); },
  voiceNormalize(text) { return this.post('/api/voice/normalize', { text }); },
  voiceTts(text) { return this.post('/api/voice/tts', { text }); },
};

const DEMO_USER_ID = 'u_demo_zhang';
function currentUserId() { return localStorage.getItem('medagent_user_id') || DEMO_USER_ID; }
function setCurrentUserId(id) { localStorage.setItem('medagent_user_id', id); }
