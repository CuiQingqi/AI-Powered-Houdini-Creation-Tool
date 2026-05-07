/**
 * Node Graph Panel — simplified Canvas-based Houdini node network visualization.
 *
 * No external dependencies. Pure Canvas 2D rendering.
 */

const NodeGraph = {
  _nodes: [],
  _connections: [],
  _networkPath: '/obj',
  _dragging: false,
  _dragStart: null,
  _offset: { x: 0, y: 0 },
  _scale: 1.0,
  _hoveredNode: null,

  // Visual config
  NODE_W: 100,
  NODE_H: 28,
  COLORS: {
    display: '#4caf50',
    render: '#e53935',
    default: '#42a5f5',
    bypass: '#888888',
    special: '#f0a040',
  },

  init() {
    this.canvas = document.getElementById('node-graph-canvas');
    this.placeholder = document.getElementById('graph-placeholder');
    this.pathLabel = document.getElementById('graph-path');
    this.ctx = this.canvas.getContext('2d');

    this._resize();
    window.addEventListener('resize', () => this._resize());

    // Mouse events
    this.canvas.addEventListener('click', (e) => this._onClick(e));
    this.canvas.addEventListener('mousemove', (e) => this._onMove(e));
    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      this._scale = Math.max(0.3, Math.min(3, this._scale - e.deltaY * 0.001));
      this.render();
    });

    EventBus.on('node_graph_update', (data) => this.update(data));
  },

  update(data) {
    if (!data || data.status === 'error') return;

    const d = data.data || data;
    if (d.nodes) this._nodes = d.nodes;
    if (d.connections) this._connections = d.connections;
    if (d.network_path) {
      this._networkPath = d.network_path;
      this.pathLabel.textContent = d.network_path;
    }

    if (this._nodes.length > 0) {
      this.canvas.style.display = 'block';
      this.placeholder.style.display = 'none';
      this.render();
    }
  },

  _resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = rect.width * devicePixelRatio;
    this.canvas.height = rect.height * devicePixelRatio;
    this.canvas.style.width = rect.width + 'px';
    this.canvas.style.height = rect.height + 'px';
    this.render();
  },

  render() {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.scale(devicePixelRatio, devicePixelRatio);
    const cw = w / devicePixelRatio;
    const ch = h / devicePixelRatio;

    // Center offset
    const ox = cw / 2 + this._offset.x;
    const oy = ch / 2 + this._offset.y;

    // Build position map
    const posMap = {};
    this._nodes.forEach(n => {
      posMap[n.path] = {
        x: ox + (n.position ? n.position[0] * this._scale * 40 : 0),
        y: oy + (n.position ? n.position[1] * this._scale * 40 : 0),
      };
    });

    // Draw connections
    this._connections.forEach(conn => {
      const from = posMap[conn.from_path];
      const to = posMap[conn.to_path];
      if (!from || !to) return;

      ctx.strokeStyle = '#555';
      ctx.lineWidth = 1.5 * this._scale;
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      // Curved path
      const midX = (from.x + to.x) / 2;
      ctx.bezierCurveTo(midX, from.y, midX, to.y, to.x, to.y);
      ctx.stroke();

      // Arrowhead
      const angle = Math.atan2(to.y - from.y, to.x - from.x);
      const ax = to.x - Math.cos(angle) * 8;
      const ay = to.y - Math.sin(angle) * 8;
      ctx.fillStyle = '#555';
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(
        ax - Math.cos(angle - 1.2) * 6,
        ay - Math.sin(angle - 1.2) * 6
      );
      ctx.lineTo(
        ax - Math.cos(angle + 1.2) * 6,
        ay - Math.sin(angle + 1.2) * 6
      );
      ctx.closePath();
      ctx.fill();
    });

    // Draw nodes
    this._nodes.forEach(n => {
      const pos = posMap[n.path];
      if (!pos) return;

      const nw = this.NODE_W * this._scale;
      const nh = this.NODE_H * this._scale;
      const x = pos.x - nw / 2;
      const y = pos.y - nh / 2;

      // Color
      let color = this.COLORS.default;
      if (n.is_display) color = this.COLORS.display;
      if (n.is_bypass) color = this.COLORS.bypass;
      if (n.is_display && n.is_render) color = this.COLORS.display;

      // Background
      const isHovered = this._hoveredNode && this._hoveredNode.path === n.path;
      ctx.fillStyle = isHovered ? '#3a3a3a' : '#2a2a2a';
      ctx.strokeStyle = color;
      ctx.lineWidth = isHovered ? 2 : 1;
      this._roundRect(ctx, x, y, nw, nh, 4);

      // Label
      ctx.fillStyle = '#ccc';
      ctx.font = `${10 * this._scale}px ${getComputedStyle(document.body).fontFamily}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const label = n.name || n.path.split('/').pop();
      ctx.fillText(label, pos.x, pos.y);
    });

    ctx.restore();
  },

  _roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  },

  _getNodeAt(mx, my) {
    const cw = this.canvas.width / devicePixelRatio;
    const ch = this.canvas.height / devicePixelRatio;
    const ox = cw / 2 + this._offset.x;
    const oy = ch / 2 + this._offset.y;

    for (let i = this._nodes.length - 1; i >= 0; i--) {
      const n = this._nodes[i];
      const pos = n.position || [0, 0];
      const x = ox + pos[0] * this._scale * 40 - (this.NODE_W * this._scale) / 2;
      const y = oy + pos[1] * this._scale * 40 - (this.NODE_H * this._scale) / 2;
      const nw = this.NODE_W * this._scale;
      const nh = this.NODE_H * this._scale;
      if (mx >= x && mx <= x + nw && my >= y && my <= y + nh) {
        return n;
      }
    }
    return null;
  },

  _onClick(e) {
    const rect = this.canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const node = this._getNodeAt(mx, my);
    if (node) {
      EventBus.emit('select_node', node);
    }
  },

  _onMove(e) {
    const rect = this.canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const prev = this._hoveredNode;
    this._hoveredNode = this._getNodeAt(mx, my);
    if (this._hoveredNode !== prev) {
      this.render();
      this.canvas.style.cursor = this._hoveredNode ? 'pointer' : 'default';
    }
  }
};
