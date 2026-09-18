import html
import logging
import socket
import threading
import time
from pathlib import Path
from string import Template

import webview


LOG_PATH = Path(__file__).resolve().parent / "desktop_client.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
    force=True,
)


LOADING_HTML = Template(
    """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PCB Defect Studio</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #07111f;
      --panel: #0d1a2b;
      --panel-2: #12233a;
      --border: rgba(118, 160, 208, 0.22);
      --text: #edf5ff;
      --muted: #97abc2;
      --cyan: #62dcff;
      --teal: #27d8b5;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at top left, rgba(98, 220, 255, 0.12), transparent 28%),
        radial-gradient(circle at bottom right, rgba(39, 216, 181, 0.10), transparent 24%),
        linear-gradient(135deg, #06101c 0%, #091626 42%, #0f2037 100%);
      color: var(--text);
      font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    }
    .panel {
      width: min(560px, calc(100vw - 40px));
      padding: 34px;
      border-radius: 28px;
      background: linear-gradient(180deg, rgba(12, 24, 40, 0.98), rgba(9, 18, 31, 0.96));
      border: 1px solid var(--border);
      box-shadow: 0 22px 64px rgba(0, 0, 0, 0.32);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 22px;
    }
    .brand-mark {
      width: 52px;
      height: 52px;
      border-radius: 16px;
      display: grid;
      place-items: center;
      font-weight: 800;
      letter-spacing: 0.08em;
      background: linear-gradient(135deg, rgba(98, 220, 255, 0.28), rgba(39, 216, 181, 0.18));
      border: 1px solid rgba(98, 220, 255, 0.24);
    }
    .brand small { display: block; color: var(--muted); margin-top: 4px; }
    h1 { margin: 0; font-size: 1.6rem; }
    p { margin: 0; color: var(--muted); line-height: 1.8; }
    .status-row {
      margin-top: 22px;
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .spinner {
      width: 26px;
      height: 26px;
      border-radius: 50%;
      border: 3px solid rgba(98, 220, 255, 0.16);
      border-top-color: var(--cyan);
      animation: spin 0.9s linear infinite;
      flex-shrink: 0;
    }
    .tips {
      margin-top: 18px;
      padding: 16px 18px;
      border-radius: 18px;
      background: rgba(18, 35, 58, 0.92);
      border: 1px solid rgba(118, 160, 208, 0.12);
      color: var(--muted);
      font-size: 0.95rem;
    }
    .is-error .spinner { border-top-color: #ff6b7d; animation: none; }
    .is-error .tips { color: #ffd7dc; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <section class="panel${state_class}">
    <div class="brand">
      <div class="brand-mark">PCB</div>
      <div>
        <h1>Defect Studio</h1>
        <small>Desktop Inspection Client</small>
      </div>
    </div>
    <p>${message}</p>
    <div class="status-row">
      <div class="spinner"></div>
      <strong>${status}</strong>
    </div>
    <div class="tips">${tips}</div>
  </section>
  <script>
    const targetUrl = "${target_url}";
    const probeUrl = "${probe_url}";
    const pollDelay = 600;

    function tryConnect() {
      const probe = new Image();
      probe.onload = () => window.location.replace(targetUrl);
      probe.onerror = () => window.setTimeout(tryConnect, pollDelay);
      probe.src = probeUrl + "?_ts=" + Date.now();
    }

    window.setTimeout(tryConnect, pollDelay);
  </script>
</body>
</html>
"""
)


class WindowControls:
    def __init__(self) -> None:
        self._window = None
        self.is_maximized = False
        self._action_lock = threading.Lock()
        self._last_action_name = ""
        self._last_action_at = 0.0

    def _should_run_action(self, action_name: str, cooldown_seconds: float = 0.25) -> bool:
        with self._action_lock:
            now = time.monotonic()
            if action_name == self._last_action_name and (now - self._last_action_at) < cooldown_seconds:
                logging.info("Ignored duplicate window action: %s", action_name)
                return False

            self._last_action_name = action_name
            self._last_action_at = now
            return True

    def attach(self, window: webview.Window) -> None:
        self._window = window
        logging.info("Window controls attached")

    def minimize(self) -> bool:
        if not self._should_run_action("minimize"):
            return True
        logging.info("Window minimize requested")
        if self._window:
            self._window.minimize()
        return True

    def toggle_maximize(self) -> bool:
        if not self._should_run_action("toggle_maximize"):
            return self.is_maximized
        logging.info("Window maximize toggle requested")
        if self._window:
            if self.is_maximized:
                self._window.restore()
            else:
                self._window.maximize()
            self.is_maximized = not self.is_maximized
        return self.is_maximized

    def toggle_fullscreen(self) -> bool:
        # Backward-compatible alias for older frontend builds.
        return self.toggle_maximize()

    def close(self) -> bool:
        if not self._should_run_action("close"):
            return True
        logging.info("Window close requested")
        if self._window:
            self._window.destroy()
        return True

    def choose_model(self) -> str:
        if not self._should_run_action("choose_model", cooldown_seconds=0.4):
            return ""
        logging.info("Model chooser requested")
        if not self._window:
            return ""

        selected = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("YOLO 模型 (*.pt)", "所有文件 (*.*)"),
        )
        if not selected:
            logging.info("Model chooser cancelled")
            return ""

        model_path = str(selected[0])
        logging.info("Model selected: %s", model_path)
        return model_path


def build_loading_html(
    message: str,
    status: str,
    tips: str,
    target_url: str,
    probe_url: str,
    is_error: bool = False,
) -> str:
    return LOADING_HTML.substitute(
        message=html.escape(message),
        status=html.escape(status),
        tips=html.escape(tips),
        target_url=html.escape(target_url),
        probe_url=html.escape(probe_url),
        state_class=" is-error" if is_error else "",
    )


def find_available_port(host: str = "127.0.0.1", start_port: int = 7860, end_port: int = 7999) -> int:
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex((host, port)) != 0:
                logging.info("Selected available port %s", port)
                return port
    raise RuntimeError(f"未找到可用端口，范围: {start_port}-{end_port}")


def wait_for_server(host: str, port: int, timeout_seconds: int = 45) -> None:
    deadline = time.time() + timeout_seconds
    logging.info("Waiting for server at %s:%s", host, port)
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                logging.info("Server is reachable at %s:%s", host, port)
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("本地服务启动超时，请检查模型文件和运行环境。")


def run_local_server(host: str, port: int) -> None:
    logging.info("Server thread started")
    try:
        from app import run_server

        logging.info("Imported app.run_server successfully")
        run_server(host=host, port=port, open_browser=False)
    except Exception:
        logging.exception("Local server crashed during startup")
        raise


def background_bootstrap(host: str, port: int) -> None:
    logging.info("Background bootstrap entered")
    server_thread = threading.Thread(target=run_local_server, args=(host, port), daemon=True, name="local-server")
    server_thread.start()
    logging.info("Local server thread launched")

    try:
        wait_for_server(host, port)
    except Exception:
        logging.exception("Failed while waiting for server")
        return
    logging.info("Server startup confirmed by background worker")


def start_bootstrap_async(host: str, port: int) -> None:
    logging.info("Scheduling background bootstrap thread")
    threading.Thread(
        target=background_bootstrap,
        args=(host, port),
        daemon=True,
        name="bootstrap-worker",
    ).start()


def main() -> None:
    logging.info("Desktop client starting")
    host = "127.0.0.1"
    port = find_available_port(host=host, start_port=7860)
    target_url = f"http://{host}:{port}"
    probe_url = f"{target_url}/examples/missing_hole"

    controls = WindowControls()
    window = webview.create_window(
        "PCB 缺陷检测系统",
        html=build_loading_html(
            message="客户端正在初始化本地检测服务和页面资源。",
            status="启动中",
            tips="首次打开会稍慢，YOLO 模型将在首次执行检测时再加载。",
            target_url=target_url,
            probe_url=probe_url,
        ),
        js_api=controls,
        width=1480,
        height=960,
        min_size=(1180, 760),
        background_color="#07111f",
        text_select=True,
        frameless=True,
        easy_drag=False,
        shadow=False,
    )
    logging.info("Window created")
    controls.attach(window)
    logging.info("Entering webview event loop")
    webview.start(lambda: start_bootstrap_async(host, port), debug=False)


if __name__ == "__main__":
    main()
