/**
 * Settings — modal + bottom bar + chat toolbar context meter.
 */

const Settings = {
  _models: {
    deepseek:[{v:'deepseek-chat',n:'Chat (fast)'},{v:'deepseek-reasoner',n:'Reasoner (pro)'}],
    openai:[{v:'gpt-4o',n:'GPT-4o'},{v:'gpt-4.1',n:'4.1 (pro)'},{v:'o4-mini',n:'o4-mini (flash)'}],
    anthropic:[{v:'claude-sonnet-4-20250514',n:'Sonnet 4 (fast)'},{v:'claude-opus-4-20250514',n:'Opus 4 (pro)'},{v:'claude-haiku-4-20250514',n:'Haiku 4 (flash)'}],
    ollama:[{v:'llama3',n:'Llama 3'},{v:'mixtral',n:'Mixtral'}],
  },
  _providerNames: {deepseek:'DeepSeek',openai:'OpenAI',anthropic:'Claude',ollama:'Ollama'},

  init() {
    this.providerEl = document.getElementById('cfg-provider');
    this.modelPresetEl = document.getElementById('cfg-model-preset');
    this.modelEl = document.getElementById('cfg-model');
    this.contextEl = document.getElementById('cfg-context');
    this.apikeyEl = document.getElementById('cfg-apikey');
    this.baseUrlEl = document.getElementById('cfg-baseurl');
    this.obsidianEl = document.getElementById('cfg-obsidian');
    this.statusEl = document.getElementById('settings-status');
    this.modal = document.getElementById('settings-modal');
    this.aiInfo = document.getElementById('ai-info');
    this.dotAi = document.getElementById('dot-ai');
    this.ctxMeter = document.getElementById('ctx-meter');

    this.aiInfo.addEventListener('click', () => this.open());
    document.getElementById('btn-close-modal').addEventListener('click', () => this.close());
    document.querySelector('#settings-modal .modal-overlay').addEventListener('click', () => this.close());
    this.providerEl.addEventListener('change', () => this.updateModels());
    this.modelPresetEl.addEventListener('change', () => {
      if (this.modelPresetEl.value) this.modelEl.value = this.modelPresetEl.value;
    });
    document.getElementById('btn-save-settings').addEventListener('click', () => this.save());

    // RAG toggle
    const ragToggle = document.getElementById('toggle-search');
    if (ragToggle) {
      ragToggle.addEventListener('change', () => {
        if (ragToggle.checked && !this._obsidianPath) {
          alert('Configure Obsidian vault path in Settings first (click bottom-left AI info)');
          ragToggle.checked = false;
        }
      });
    }

    this.load();
  },

  open() { this.modal.classList.remove('hidden'); },
  close() { this.modal.classList.add('hidden'); },

  load() {
    fetch('/api/settings').then(r => r.json()).then(cfg => {
      this.providerEl.value = cfg.provider || 'deepseek';
      this.modelEl.value = cfg.openai_model || 'deepseek-chat';
      this.contextEl.value = String(cfg.context_limit || 128000);
      this.apikeyEl.value = cfg.openai_api_key || '';
      this.baseUrlEl.value = cfg.openai_base_url || 'https://api.deepseek.com/v1';
      if (this.obsidianEl) this.obsidianEl.value = cfg.obsidian_vault_path || '';
      this._obsidianPath = cfg.obsidian_vault_path || '';
      this.updateModels();
      this.updateBar(cfg);
      this.updateContextMeter(parseInt(cfg.context_limit) || 128000);
    }).catch(() => {});
  },

  updateContextMeter(limit) {
    if (this.ctxMeter) {
      const limStr = limit >= 1000000 ? '1M' : Math.round(limit/1000) + 'K';
      this.ctxMeter.textContent = '0 / ' + limStr;
    }
  },

  updateBar(cfg) {
    const provider = cfg.provider || this.providerEl.value;
    const model = cfg.openai_model || this.modelEl.value;
    const ctx = cfg.context_limit || parseInt(this.contextEl.value) || 128000;
    const hasKey = !!(cfg.openai_api_key && cfg.openai_api_key.length > 8);
    const ctxStr = ctx >= 1000000 ? '1M' : Math.round(ctx/1000) + 'K';
    const name = this._providerNames[provider] || provider;
    this.aiInfo.textContent = name + ' / ' + model + ' / ' + ctxStr;
    this.aiInfo.className = hasKey ? 'ai-info-text configured' : 'ai-info-text';
    this.dotAi.className = hasKey ? 'stat-dot on' : 'stat-dot off';
    this.updateContextMeter(ctx);
  },

  updateAiStatus(aiConfigured, provider, model, ctx) {
    if (aiConfigured) {
      const ctxStr = (ctx || 128000) >= 1000000 ? '1M' : Math.round((ctx||128000)/1000) + 'K';
      const name = this._providerNames[provider] || provider || '';
      this.aiInfo.textContent = (name + ' / ' + (model||'') + ' / ' + ctxStr);
      this.aiInfo.className = 'ai-info-text configured';
      this.dotAi.className = 'stat-dot on';
      this.updateContextMeter(ctx || 128000);
    } else {
      this.aiInfo.textContent = 'Click to configure AI';
      this.aiInfo.className = 'ai-info-text';
      this.dotAi.className = 'stat-dot off';
    }
  },

  async save() {
    const provider = this.providerEl.value;
    this._obsidianPath = this.obsidianEl ? this.obsidianEl.value : '';
    const data = {
      provider, model: this.modelEl.value,
      context_limit: parseInt(this.contextEl.value),
      openai_api_key: this.apikeyEl.value,
      openai_base_url: this.baseUrlEl.value,
      openai_model: this.modelEl.value,
      obsidian_vault_path: this._obsidianPath,
    };
    try {
      const r = await fetch('/api/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      const result = await r.json();
      if (result.ok) {
        this.statusEl.className = 'settings-status ok';
        this.statusEl.textContent = 'Saved!';
        this.updateBar(data);
        App.send({type:'reload_ai'});
        setTimeout(() => { this.statusEl.textContent = ''; this.close(); }, 1000);
      } else {
        this.statusEl.className = 'settings-status err';
        this.statusEl.textContent = result.error || 'Save failed';
      }
    } catch(e) {
      this.statusEl.className = 'settings-status err';
      this.statusEl.textContent = 'Network error';
    }
  },
};
