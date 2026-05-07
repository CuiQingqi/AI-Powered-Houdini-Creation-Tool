/**
 * Tool Execution Log — real-time log of MCP tool calls.
 */

const ToolLog = {
  MAX_ENTRIES: 500,
  _entries: [],
  _filter: 'all',

  init() {
    this.container = document.getElementById('log-entries');
    this.emptyMsg = 'Waiting for tool calls from Claude Code...';

    // Filter buttons
    document.querySelectorAll('.log-filter').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.log-filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this._filter = btn.dataset.filter;
        this.render();
      });
    });

    document.getElementById('btn-clear-log').addEventListener('click', () => {
      this._entries = [];
      this.render();
    });

    EventBus.on('tool_executed', (data) => this.addEntry(data));
  },

  addEntry(data) {
    this._entries.unshift({
      time: data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString(),
      tool: data.tool || 'unknown',
      status: data.status || 'error',
      message: data.message || '',
      elapsed: data.elapsed_ms || 0,
    });

    // Trim
    if (this._entries.length > this.MAX_ENTRIES) {
      this._entries.length = this.MAX_ENTRIES;
    }

    this.render();
  },

  render() {
    const filtered = this._filter === 'all'
      ? this._entries
      : this._entries.filter(e => e.status === this._filter);

    if (filtered.length === 0) {
      this.container.innerHTML = `<div class="log-empty">${this.emptyMsg}</div>`;
      return;
    }

    this.container.innerHTML = filtered.map(e => `
      <div class="log-entry">
        <span class="log-icon ${e.status}">${e.status === 'success' ? '✓' : '✗'}</span>
        <span class="log-time">${e.time}</span>
        <span class="log-tool">${this._escape(e.tool)}</span>
        <span class="log-msg ${e.status === 'error' ? 'error-msg' : ''}">${this._escape(e.message)}</span>
        <span class="log-elapsed">${e.elapsed}ms</span>
      </div>
    `).join('');
  },

  _escape(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }
};
