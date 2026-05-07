/**
 * Workflow Tree — Project → Module → Operation → Nodetask hierarchy.
 */

const WorkflowTree = {
  _modules: [],
  _projectName: '',
  _projectDesc: '',

  init() {
    this.treeEl = document.getElementById('workflow-tree');
    EventBus.on('phase_done', (data) => this.onPhaseDone(data));
    EventBus.on('task_start', (data) => this.onTaskStart(data));
    EventBus.on('task_done', (data) => this.onTaskDone(data));
    EventBus.on('chat_reset', () => this.clear());

    this.treeEl.addEventListener('click', (e) => {
      const hdr = e.target.closest('[data-toggle]');
      if (hdr) {
        const body = document.getElementById(hdr.dataset.toggle);
        if (body) {
          body.classList.toggle('collapsed');
          hdr.querySelector('.arrow').classList.toggle('open');
        }
      }
    });
  },

  clear() {
    this._modules = [];
    this._projectName = '';
    this._projectDesc = '';
    this.render();
  },

  onPhaseDone(data) {
    // Phase 1: project description (first ~100 chars of optimized prompt = project name)
    if (data.phase === 'optimizing') {
      // No action here — project info comes from modules phase
    }

    // Phase 2: modules defined
    if (data.phase === 'modules' && data.modules) {
      if (data.project_name) this._projectName = data.project_name;
      if (data.project_description) this._projectDesc = data.project_description;
      this._modules = data.modules.map(m => ({
        id: m.module_id,
        name: m.module_name,
        description: m.description || '',
        operations: [],
      }));
      this.render();
    }

    // Phase 3: operations for a module
    if (data.phase === 'operations' && data.module_id) {
      const mod = this._modules.find(m => m.id === data.module_id);
      if (mod) {
        mod.operations = [];
        for (let i = 0; i < (data.op_count || 0); i++) {
          mod.operations.push({ name: 'Op ' + (i + 1), tasks: [] });
        }
        this.render();
      }
    }

    // Phase 4: compiled tasks
    if (data.phase === 'compiling' && data.tasks) {
      data.tasks.forEach((t, idx) => {
        const mod = this._modules.find(m => m.name === t.module_name);
        if (mod && mod.operations.length > 0) {
          const opIdx = idx % mod.operations.length;
          mod.operations[opIdx].tasks.push({
            id: t.task_id, name: t.operation_name, action: t.action_type, status: 'pending',
          });
        }
      });
      this.render();
    }
  },

  onTaskStart(data) { this._updateTask(data.task_id, 'running'); this.render(); },
  onTaskDone(data) { this._updateTask(data.task_id, data.status); this.render(); },

  _updateTask(taskId, status) {
    for (const mod of this._modules)
      for (const op of mod.operations)
        for (const t of op.tasks)
          if (t.id === taskId) { t.status = status; return; }
  },

  restoreFromSaved(data) {
    this._projectName = data.name || '';
    this._projectDesc = data.detailed_requirement || '';
    const mods = data.modules || [];
    const tasks = data.tasks || [];

    this._modules = mods.map(m => ({
      id: m.module_id || '',
      name: m.module_name || '',
      description: m.description || '',
      operations: (m.operations || []).map((op, oi) => ({
        name: op.operation_name || ('Op ' + (oi + 1)),
        tasks: [],
      })),
    }));

    tasks.forEach((t, idx) => {
      const mod = this._modules.find(m => m.name === t.module_name);
      if (mod && mod.operations.length > 0) {
        const opIdx = idx % mod.operations.length;
        mod.operations[opIdx].tasks.push({
          id: t.task_id, name: t.operation_name, action: t.action_type,
          status: t.status || 'pending',
        });
      }
    });
    this.render();
  },

  render() {
    if (this._modules.length === 0) {
      this.treeEl.innerHTML = '<div class="tree-empty">Send a message to start</div>';
      return;
    }

    let html = '';

    // Project name (if available from modules)
    if (this._projectName) {
      html += `<div class="tree-project-name">${this._esc(this._projectName)}</div>`;
    }
    if (this._projectDesc) {
      html += `<div class="tree-project-desc">${this._esc(this._projectDesc).substring(0, 200)}</div>`;
    }

    for (let mi = 0; mi < this._modules.length; mi++) {
      const mod = this._modules[mi];
      const modDone = mod.operations.every(op => op.tasks.every(t => t.status === 'done'));
      const modId = `mod-${mi}`;

      html += `<div class="tree-module">`;
      html += `<div class="tree-module-header" data-toggle="${modId}">`;
      html += `<span class="arrow open">&#9654;</span>`;
      html += `<span class="mod-name">${this._esc(mod.name)}</span>`;
      html += modDone ? ' <span class="mod-done">done</span>' : '';
      html += `</div>`;
      if (mod.description) {
        html += `<div class="tree-module-desc">${this._esc(mod.description).substring(0, 120)}</div>`;
      }
      html += `<div class="tree-module-body" id="${modId}">`;

      for (let oi = 0; oi < mod.operations.length; oi++) {
        const op = mod.operations[oi];
        const opDone = op.tasks.length > 0 && op.tasks.every(t => t.status === 'done');
        const opId = `op-${mi}-${oi}`;

        html += `<div class="tree-op">`;
        html += `<div class="tree-op-header" data-toggle="${opId}">`;
        html += `<span class="arrow">&#9654;</span>`;
        html += `<span>${this._esc(op.name)}</span>`;
        html += opDone ? ' <span class="op-done">OK</span>' : '';
        html += `</div>`;
        html += `<div class="tree-op-body collapsed" id="${opId}">`;

        for (const task of op.tasks) {
          html += `<div class="tree-task">`;
          html += `<span class="task-dot ${task.status}"></span>`;
          html += `<span class="task-id">${task.id}</span> `;
          html += `<span class="task-text">${this._esc(task.name || task.action)}</span>`;
          html += `</div>`;
        }
        html += `</div></div>`;
      }
      html += `</div></div>`;
    }

    this.treeEl.innerHTML = html;
  },

  _esc(s) {
    const d = document.createElement('div');
    d.textContent = String(s || '');
    return d.innerHTML;
  }
};
