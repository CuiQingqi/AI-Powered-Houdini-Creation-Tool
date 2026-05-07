"""
Viewport screenshot capture.

Captures the current Houdini viewport as a base64-encoded PNG for use
in the auxiliary Web UI.
"""

import base64
import os
import tempfile


def capture_viewport_base64(resolution: tuple = (800, 600)) -> str:
    """Capture the Houdini viewport and return as base64 PNG data URL.

    Args:
        resolution: (width, height) tuple for the screenshot.

    Returns:
        A data URL string: "data:image/png;base64,..." or empty string on failure.
    """
    try:
        import hou

        # Use flipbook to capture current viewport
        width, height = resolution
        flip_options = hou.flipbookOptions()
        flip_options.setSize((width, height))

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Capture the active viewport
            viewport = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
            if viewport is None:
                viewport = hou.ui.curDesktop().paneTabOfType(hou.paneTabType.SceneViewer)

            if viewport:
                viewport.flipbookSettings().setSize((width, height))
                viewport.flipbook(stash_frame=False, output_to_file=tmp_path)

                with open(tmp_path, "rb") as f:
                    img_data = f.read()

                b64 = base64.b64encode(img_data).decode("ascii")
                return f"data:image/png;base64,{b64}"
            else:
                return ""
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except Exception:
        return ""


def capture_viewport_simple() -> str:
    """Simplified viewport capture using hou.hscript().

    Falls back to using the 'viewwrite' hscript command if flipbook fails.
    """
    try:
        import hou

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            hou.hscript(f"viewwrite -q 100 {tmp_path}")
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                with open(tmp_path, "rb") as f:
                    img_data = f.read()
                b64 = base64.b64encode(img_data).decode("ascii")
                return f"data:image/png;base64,{b64}"
            return ""
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception:
        return ""
