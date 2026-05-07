/**
 * Error Bar — displays errors and warnings from tool execution.
 */

const ErrorBar = {
  _errors: [],
  MAX_ERRORS: 50,

  init() {
    this.bar = document.getElementById('error-bar');
    this.content = document.getElementById('error-bar-content');
    this.countBadge = document.getElementById('error-count');
    this.title = document.getElementById('error-bar-title');

    document.getElementById('btn-dismiss-errors').addEventListener('click', () => {
      this._errors = [];
      this.render();
    });

    EventBus.on('error', (data) => this.addError(data));
  },

  addError(data) {
    this._errors.unshift({
      time: data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString(),
      tool: data.tool || 'unknown',
      message: data.message || 'Unknown error',
      severity: data.severity || 'error',
    });

    if (this._errors.length > this.MAX_ENTRIES) {
      this._errors.length = this.MAX_ENTRIES;
    }

    this.render();
  },

  render() {
    if (this._errors.length === 0) {
      this.bar.classList.add('hidden');
      this.countBadge.classList.add('hidden');
      return;
    }

    this.bar.classList.remove('hidden');
    this.countBadge.classList.remove('hidden');
    this.countBadge.textContent = this._errors.length;
    this.title.textContent = `Warnings / Errors (${this._errors.length})`;

    this.content.innerHTML = this._errors.map(e => `
      <div class="error-card">
        <span class="error-card-severity severity-${e.severity}">${e.severity.toUpperCase()}</span>
        <span style="color:var(--text-dim);min-width:60px">${e.time}</span>
        <span style="color:var(--text-bright);min-width:140px">${this._esc(e.tool)}</span>
        <span style="flex:1;color:${e.severity === 'error' ? 'var(--red)' : 'var(--accent)'}">${this._esc(e.message)}</span>
      </div>
    `).join('');
  },

  _esc(s) {
    const div = document.createElement('div');
    div.textContent = String(s);
    return div.innerHTML;
  }
};
