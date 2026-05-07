/**
 * Viewport Panel — displays viewport screenshots pushed from Houdini.
 */

const ViewportPanel = {
  init() {
    this.img = document.getElementById('viewport-img');
    this.placeholder = document.getElementById('viewport-placeholder');
    this.autoRefresh = document.getElementById('auto-refresh');
    this.btnRefresh = document.getElementById('btn-refresh');

    this.btnRefresh.addEventListener('click', () => this.requestCapture());

    EventBus.on('viewport_update', (data) => this.show(data));
  },

  show(data) {
    if (!data.image_base64) return;
    this.img.src = data.image_base64;
    this.img.style.display = 'block';
    this.placeholder.style.display = 'none';
  },

  requestCapture() {
    App.send({ type: 'request_viewport' });
  }
};
