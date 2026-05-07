/**
 * Parameter Inspector — modal popup for node details.
 */

const Inspector = {
  init() {
    this.modal = document.getElementById('inspector-modal');
    this.content = document.getElementById('inspector-content');
    this.title = document.getElementById('inspector-title');

    document.getElementById('btn-close-inspector').addEventListener('click', () => this.hide());
    document.querySelector('#inspector-modal .modal-overlay').addEventListener('click', () => this.hide());

    EventBus.on('select_node', (node) => this.inspectNode(node));
    EventBus.on('node_info', (data) => this.showDetails(data));
  },

  show() { this.modal.classList.remove('hidden'); },
  hide() { this.modal.classList.add('hidden'); },

  inspectNode(node) {
    this.title.textContent = node.name || 'Node';
    this.content.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-dim)">Loading...</div>';
    this.show();
    App.send({ type: 'get_node_info', node_path: node.path });
  },

  showDetails(data) {
    if (!data || data.status === 'error') {
      this.content.innerHTML = `<div style="text-align:center;padding:20px;color:var(--red)">${data?.message || 'Failed'}</div>`;
      return;
    }

    const d = data.data || data;
    this.title.textContent = d.name || 'Node';

    let html = '';
    html += `<div class="inspector-node-header">${this._esc(d.name)}</div>`;
    html += `<span class="inspector-node-type">${this._esc(d.type)}</span>`;

    html += '<div class="inspector-flags">';
    html += `<span class="inspector-flag ${d.is_display ? 'flag-set' : 'flag-unset'}">Display</span>`;
    html += `<span class="inspector-flag ${d.is_render ? 'flag-set' : 'flag-unset'}">Render</span>`;
    html += `<span class="inspector-flag ${d.is_bypass ? 'flag-set' : 'flag-unset'}">Bypass</span>`;
    html += '</div>';

    html += `<div class="inspector-section">`;
    html += `<div class="inspector-section-title">Path</div>`;
    html += `<div style="font-family:var(--font-mono);font-size:11px;color:var(--text-dim)">${this._esc(d.path)}</div>`;
    html += `</div>`;

    if (d.parameters && d.parameters.length > 0) {
      html += `<div class="inspector-section">`;
      html += `<div class="inspector-section-title">Parameters (${d.non_default_params || d.parameters.length})</div>`;
      d.parameters.slice(0, 15).forEach(p => {
        html += `<div class="param-row">`;
        html += `<span class="param-name">${this._esc(p.name)}</span>`;
        html += `<span class="param-value">${this._esc(String(p.value))}</span>`;
        html += `</div>`;
      });
      html += `</div>`;
    }

    if (d.inputs && d.inputs.length > 0) {
      html += `<div class="inspector-section">`;
      html += `<div class="inspector-section-title">Inputs</div>`;
      d.inputs.forEach((inp, i) => {
        html += `<div class="connection-row"><span class="connection-idx">[${i}]</span>${this._esc(inp)}</div>`;
      });
      html += `</div>`;
    }

    const errors = d.errors || [];
    if (errors.length > 0) {
      html += `<div class="inspector-section">`;
      html += `<div class="inspector-section-title">Errors</div>`;
      errors.forEach(e => {
        html += `<div style="color:var(--red);font-size:11px;margin:2px 0">${this._esc(String(e))}</div>`;
      });
      html += `</div>`;
    }

    this.content.innerHTML = html;
  },

  _esc(s) {
    const div = document.createElement('div');
    div.textContent = String(s);
    return div.innerHTML;
  }
};
