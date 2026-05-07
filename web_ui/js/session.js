/**
 * Session Bar — connection status, uptime, scene info.
 */

const SessionBar = {
  init() {
    this.dot = document.getElementById('connection-dot');
    this.hipFile = document.getElementById('hip-file');
    this.uptime = document.getElementById('uptime');

    EventBus.on('connection_status', (data) => this.update(data));

    // Start uptime counter
    this._startTime = Date.now();
    setInterval(() => this.tickUptime(), 1000);
  },

  update(data) {
    if (data.houdini_connected) {
      this.dot.className = 'dot connected';
    } else {
      this.dot.className = 'dot disconnected';
    }

    if (data.hip_file) {
      this.hipFile.textContent = data.hip_file;
    }

    if (data.uptime_seconds !== undefined) {
      this._startTime = Date.now() - (data.uptime_seconds * 1000);
    }
  },

  tickUptime() {
    const elapsed = Math.floor((Date.now() - this._startTime) / 1000);
    const h = Math.floor(elapsed / 3600);
    const m = Math.floor((elapsed % 3600) / 60);
    const s = elapsed % 60;
    this.uptime.textContent =
      `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
};
