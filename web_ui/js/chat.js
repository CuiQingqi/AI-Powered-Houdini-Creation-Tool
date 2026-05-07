/**
 * Chat Panel — user input for AI conversation + workflow display.
 */

const Chat = {
  ws: null,
  _streamingEl: null,
  _streamingBuffer: '',
  _generating: false,
  _imageBase64: '',

  init() {
    this.messagesEl = document.getElementById('chat-messages');
    this.inputEl = document.getElementById('chat-input');
    this.sendBtn = document.getElementById('btn-send');
    this.cancelBtn = document.getElementById('btn-cancel');
    this.attachBtn = document.getElementById('btn-attach-image');
    this.fileInput = document.getElementById('file-input');
    this.imagePreview = document.getElementById('image-preview');
    this.previewImg = document.getElementById('preview-img');
    this.removeImgBtn = document.getElementById('btn-remove-image');

    // Button events
    if (this.sendBtn) this.sendBtn.addEventListener('click', () => this.send());
    if (this.cancelBtn) this.cancelBtn.addEventListener('click', () => this.cancel());
    if (this.attachBtn) this.attachBtn.addEventListener('click', () => { if (this.fileInput) this.fileInput.click(); });
    if (this.removeImgBtn) this.removeImgBtn.addEventListener('click', () => this.clearImage());
    if (this.fileInput) this.fileInput.addEventListener('change', (e) => this.handleFile(e));

    if (this.inputEl) {
      this.inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.send(); }
      });
      this.inputEl.addEventListener('input', () => {
        this.inputEl.style.height = 'auto';
        this.inputEl.style.height = Math.min(this.inputEl.scrollHeight, 100) + 'px';
      });
    }

    // Hint buttons
    document.querySelectorAll('.hint-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (this.inputEl) this.inputEl.value = btn.textContent;
        this.send();
      });
    });

    // Enable send button by default
    if (this.sendBtn) this.sendBtn.disabled = false;
  },

  connect(url) {
    if (!url) return;
    this.ws = new WebSocket(url);
    this.ws.onopen = () => console.log('[Chat] connected');
    this.ws.onmessage = (event) => {
      try { this.handleMessage(JSON.parse(event.data)); }
      catch(e) { console.error('[Chat] parse:', e); }
    };
    this.ws.onclose = () => console.log('[Chat] disconnected');
    this.ws.onerror = () => {};
  },

  handleMessage(msg) {
    switch (msg.type) {
      case 'chat_status':
        this.updateStatus(msg);
        break;
      case 'text_chunk':
        if (this._generating) this.appendToPhase(msg.content || '');
        else this.appendStreaming(msg.content || '');
        break;
      case 'phase':
        this.addPhaseCard(msg.phase, msg.message);
        EventBus.emit('phase', msg);
        break;
      case 'phase_done':
        this.finalizePhase();
        EventBus.emit('phase_done', msg);
        break;
      case 'task_start':
        this.addTaskCard(msg.task_id, msg.module_name, msg.operation);
        EventBus.emit('task_start', msg);
        break;
      case 'task_done':
        this.updateTaskCard(msg.task_id, msg.status);
        EventBus.emit('task_done', msg);
        break;
      case 'error':
        this.addErrorCard(msg.message || 'Unknown error');
        break;
      case 'workflow_done':
        this.addWorkflowSummary(msg);
        this.setGenerating(false);
        break;
      case 'chat_done':
        this.setGenerating(false);
        break;
      case 'chat_reset':
        this.clearMessages();
        this.setGenerating(false);
        EventBus.emit('chat_reset', {});
        break;
    }
  },

  updateStatus(msg) {
    if (!this.sendBtn) return;
    // Always enable send button (disable only during generation)
    if (!this._generating) {
      this.sendBtn.disabled = false;
    }
    if (!msg.ai_configured) {
      this.addMessage('ai', 'AI not configured. Set API key in Settings (left sidebar).');
    }
  },

  send() {
    const text = this.inputEl ? this.inputEl.value.trim() : '';
    if (!text || this._generating) return;
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.addMessage('ai', 'Not connected. Reconnecting...');
      return;
    }

    const welcome = this.messagesEl.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    this.addMessage('user', text, this._imageBase64);
    this.ws.send(JSON.stringify({type:'chat_message', content:text, image_base64:this._imageBase64}));

    if (this.inputEl) { this.inputEl.value = ''; this.inputEl.style.height = 'auto'; }
    this.clearImage();
    this.setGenerating(true);
  },

  cancel() {
    if (this.ws) this.ws.send(JSON.stringify({type:'cancel_chat'}));
    this.finalizePhase();
    this.setGenerating(false);
  },

  // ---- Messages ----

  addMessage(role, text, imageB64) {
    const el = document.createElement('div');
    el.className = 'msg-bubble msg-' + role;
    if (imageB64) {
      const img = document.createElement('img');
      img.src = imageB64;
      img.style.cssText = 'max-width:200px;max-height:150px;border-radius:4px;margin-bottom:6px;display:block';
      el.appendChild(img);
    }
    const span = document.createElement('span');
    span.textContent = text;
    el.appendChild(span);
    this.messagesEl.appendChild(el);
    this.scroll();
    return el;
  },

  addAIBubble(text) {
    const el = document.createElement('div');
    el.className = 'msg-bubble msg-ai';
    const span = document.createElement('span');
    span.className = 'streaming-cursor';
    span.textContent = text;
    el.appendChild(span);
    this.messagesEl.appendChild(el);
    this.scroll();
    return el;
  },

  appendStreaming(text) {
    if (!this._streamingEl) this._streamingEl = this.addAIBubble(text);
    else {
      this._streamingBuffer += text;
      const span = this._streamingEl.querySelector('span');
      if (span) span.textContent = this._streamingBuffer;
    }
    this.scroll();
  },

  finalizeStreaming() {
    if (this._streamingEl) {
      const span = this._streamingEl.querySelector('.streaming-cursor');
      if (span) span.classList.remove('streaming-cursor');
      this._streamingEl = null; this._streamingBuffer = '';
    }
  },

  // ---- Phase & Task Cards ----

  addPhaseCard(phase, msg) {
    const el = document.createElement('div');
    el.className = 'phase-card';
    const icons = {optimizing:'P1',modules:'P2',operations:'P3',compiling:'P4',executing:'P5'};
    const labels = {optimizing:'Optimize',modules:'Modules',operations:'Operations',compiling:'Compile',executing:'Execute'};
    el.innerHTML = '<span class="phase-icon">'+(icons[phase]||'?')+'</span><span class="phase-label">'+(labels[phase]||phase)+'</span><span class="phase-msg"><span class="phase-text"></span><span class="streaming-cursor"></span></span>';
    this.messagesEl.appendChild(el);
    this.scroll();
  },

  appendToPhase(text) {
    const cards = this.messagesEl.querySelectorAll('.phase-card');
    if (cards.length) {
      const textEl = cards[cards.length-1].querySelector('.phase-text');
      if (textEl) { textEl.textContent += text; this.scroll(); }
    }
  },

  finalizePhase() {
    const cards = this.messagesEl.querySelectorAll('.phase-card');
    if (cards.length) {
      const cursor = cards[cards.length-1].querySelector('.streaming-cursor');
      if (cursor) cursor.remove();
    }
  },

  addTaskCard(taskId, module, operation) {
    const el = document.createElement('div');
    el.className = 'task-card';
    el.dataset.taskId = taskId;
    el.innerHTML = '<span class="task-dot-ex running">...</span><span class="task-mod">' + this._esc(module||'') + '</span><span class="task-op-text">' + this._esc(operation||'') + '</span>';
    this.messagesEl.appendChild(el);
    this.scroll();
  },

  updateTaskCard(taskId, status) {
    const card = this.messagesEl.querySelector('.task-card[data-task-id="'+taskId+'"]');
    if (card) {
      const dot = card.querySelector('.task-dot-ex');
      dot.className = 'task-dot-ex ' + status;
      dot.textContent = status === 'done' ? 'OK' : 'XX';
    }
  },

  addErrorCard(msg) {
    const el = document.createElement('div');
    el.className = 'msg-bubble msg-ai';
    el.style.color = 'var(--red)';
    el.textContent = 'Error: ' + msg;
    this.messagesEl.appendChild(el);
    this.scroll();
  },

  addWorkflowSummary(msg) {
    const el = document.createElement('div');
    el.className = 'msg-bubble msg-ai';
    el.textContent = 'Done: ' + (msg.completed||0) + '/' + (msg.total||0) + ' tasks. ' + (msg.failed ? msg.failed+' failed' : '');
    this.messagesEl.appendChild(el);
    this.scroll();
  },

  setGenerating(gen) {
    this._generating = gen;
    if (this.sendBtn) this.sendBtn.disabled = gen;
    if (this.cancelBtn) this.cancelBtn.classList.toggle('hidden', !gen);
    if (this.inputEl) this.inputEl.disabled = gen;
  },

  // ---- Image ----

  handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      this._imageBase64 = reader.result;
      if (this.previewImg) this.previewImg.src = reader.result;
      if (this.imagePreview) this.imagePreview.classList.remove('hidden');
    };
    reader.readAsDataURL(file);
    if (this.fileInput) this.fileInput.value = '';
  },

  clearImage() {
    this._imageBase64 = '';
    if (this.previewImg) this.previewImg.src = '';
    if (this.imagePreview) this.imagePreview.classList.add('hidden');
  },

  clearMessages() {
    if (this.messagesEl) {
      this.messagesEl.innerHTML = '<div class="chat-welcome"><div class="welcome-icon">H</div><h2>Houdini AI</h2><p>Describe what you want to create</p></div>';
    }
    this._streamingEl = null; this._streamingBuffer = '';
  },

  scroll() { if (this.messagesEl) this.messagesEl.scrollTop = this.messagesEl.scrollHeight; },

  _esc(s) {
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }
};
