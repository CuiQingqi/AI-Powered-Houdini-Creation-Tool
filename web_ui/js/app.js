/**
 * Houdini AI — App entry point.
 */

const EventBus = {
  _listeners: {},
  on(event, callback) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(callback);
  },
  emit(event, data) {
    (this._listeners[event] || []).forEach(cb => { try { cb(data); } catch(e) { console.error(e); } });
  }
};

const App = {
  ws: null, chatWs: null, reconnectTimer: null, reconnectDelay: 1000,

  init(config) {
    this.wsUrl = config.wsUrl || `ws://${location.host}/ws/ui`;
    this.chatWsUrl = config.chatWsUrl || `ws://${location.host}/ws/chat`;

    this.connectUI();
    Settings.init();
    WorkflowTree.init();
    Chat.init();
    ViewportPanel.init();
    ToolLog.init();
    NodeGraph.init();

    // Status updates
    EventBus.on('connection_status', (data) => this.updateStatus(data));
    EventBus.on('workflow_loaded', (data) => this.onWorkflowLoaded(data));

    // Save/Load buttons
    document.getElementById('btn-save-wf').addEventListener('click', () => this.saveWorkflow());
    document.getElementById('btn-load-wf').addEventListener('click', () => this.showLoadModal());
    document.getElementById('btn-close-load').addEventListener('click', () => this.hideLoadModal());
    document.querySelector('#load-modal .modal-overlay').addEventListener('click', () => this.hideLoadModal());

    // Bridge tooltip
    const bridgeText = document.getElementById('bridge-text');
    const bridgeDot = document.getElementById('dot-bridge');
    const bridgeTt = document.getElementById('bridge-tt');
    const showBridgeHelp = () => { bridgeTt.classList.toggle('hidden'); };
    if (bridgeText) bridgeText.addEventListener('click', showBridgeHelp);
    if (bridgeDot) bridgeDot.addEventListener('click', showBridgeHelp);
    document.addEventListener('click', (e) => {
      if (bridgeTt && !bridgeTt.classList.contains('hidden') &&
          !e.target.closest('#bridge-tt') && !e.target.closest('#bridge-text') && !e.target.closest('#dot-bridge')) {
        bridgeTt.classList.add('hidden');
      }
    });

    // Chat toolbar controls
    this.thinkToggle = document.getElementById('toggle-think');
    this.searchToggle = document.getElementById('toggle-search');
    this.ctxMeter = document.getElementById('ctx-meter');
    this.bridgeInd = document.getElementById('bridge-indicator');

    this._startTime = Date.now();
    setInterval(() => this.tickUptime(), 1000);
  },

  connectUI() {
    this.ws = new WebSocket(this.wsUrl);
    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      if (!Chat.ws || Chat.ws.readyState !== WebSocket.OPEN) {
        Chat.connect(this.chatWsUrl);
      }
    };
    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        EventBus.emit(msg.type, msg.data || msg);
      } catch(e) {}
    };
    this.ws.onclose = () => {
      EventBus.emit('connection_status', { houdini_connected: false });
      this.reconnectTimer = setTimeout(() => {
        this.connectUI();
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
      }, this.reconnectDelay);
    };
  },

  updateStatus(data) {
    const bridgeDot = document.getElementById('dot-bridge');
    const bridgeText = document.getElementById('bridge-text');
    if (bridgeDot) bridgeDot.className = 'stat-dot ' + (data.houdini_connected ? 'on' : 'off');
    if (bridgeText) {
      bridgeText.textContent = data.houdini_connected ? 'Houdini: connected' : 'Houdini: disconnected';
      bridgeText.className = data.houdini_connected ? '' : 'clickable';
    }
    // Toolbar bridge indicator
    if (this.bridgeInd) {
      this.bridgeInd.textContent = data.houdini_connected ? 'Bridge: on' : 'Bridge: off';
      this.bridgeInd.className = data.houdini_connected ? 'ctx-meter' : 'ctx-meter full';
    }

    if (data.ai_configured !== undefined && Settings) {
      Settings.updateAiStatus(data.ai_configured, data.ai_provider || '', data.ai_model || '', data.context_limit || 128000);
    }
    if (data.uptime_seconds) this._startTime = Date.now() - data.uptime_seconds * 1000;
  },

  onWorkflowLoaded(data) {
    WorkflowTree.restoreFromSaved(data);
  },

  async saveWorkflow() {
    const name = prompt('Workflow name:', 'my-workflow');
    if (!name) return;
    try {
      const r = await fetch('/api/workflow/save', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({name})
      });
      const result = await r.json();
      if (result.ok) {
        alert('Workflow saved: ' + result.id);
      } else {
        alert('Save failed: ' + (result.error || 'unknown'));
      }
    } catch(e) {
      alert('Save error: ' + e.message);
    }
  },

  async showLoadModal() {
    const modal = document.getElementById('load-modal');
    const list = document.getElementById('load-list');
    modal.classList.remove('hidden');

    try {
      const r = await fetch('/api/workflows');
      const workflows = await r.json();
      if (workflows.length === 0) {
        list.innerHTML = '<div class="tree-empty">No saved workflows</div>';
        return;
      }
      list.innerHTML = workflows.map(w => `
        <div class="wf-item">
          <span class="wf-item-name" data-id="${w.id}">${this._esc(w.name)}</span>
          <span class="wf-item-meta">${w.completed_tasks}/${w.total_tasks} tasks &middot; ${w.saved_at}</span>
          <span class="wf-item-del" data-id="${w.id}">del</span>
        </div>
      `).join('');

      // Click to load
      list.querySelectorAll('.wf-item-name').forEach(el => {
        el.addEventListener('click', async () => {
          const id = el.dataset.id;
          const r = await fetch('/api/workflow/load', {
            method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id})
          });
          const result = await r.json();
          if (result.ok) {
            this.hideLoadModal();
            EventBus.emit('workflow_loaded', result.workflow);
          }
        });
      });

      // Click to delete
      list.querySelectorAll('.wf-item-del').forEach(el => {
        el.addEventListener('click', async (e) => {
          e.stopPropagation();
          const id = el.dataset.id;
          await fetch('/api/workflow/delete', {
            method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id})
          });
          this.showLoadModal(); // Refresh
        });
      });
    } catch(e) {
      list.innerHTML = '<div class="tree-empty">Error loading workflows</div>';
    }
  },

  hideLoadModal() {
    document.getElementById('load-modal').classList.add('hidden');
  },

  tickUptime() {
    const el = document.getElementById('uptime');
    if (!el) return;
    const s = Math.floor((Date.now() - this._startTime) / 1000);
    const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = s%60;
    el.textContent = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
  },

  send(msg) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  },

  _esc(s) {
    const d = document.createElement('div');
    d.textContent = String(s||'');
    return d.innerHTML;
  }
};
