# Launcher entrypoint for OmniStitch Studio EXE
import os
import sys
import threading
import webbrowser
import multiprocessing

multiprocessing.freeze_support()

if getattr(sys, 'frozen', False):
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    app_dir = os.path.abspath(os.path.dirname(sys.executable))
    os.chdir(app_dir)
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = bundle_dir

os.environ["OMNISTITCH_WORKSPACE_DIR"] = app_dir

for p in [bundle_dir, app_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

import server

# Override paths for bundled environment
server.tool_dir = bundle_dir
server.WORKSPACE_DIR = app_dir
server.NHUOM_MO_DIR = os.path.join(app_dir, "NhuomMo")
server.DATA_DIR = os.path.join(app_dir, "data")
server.OUTPUTS_DIR = os.path.join(server.DATA_DIR, "result")
server.UPLOADS_DIR = os.path.join(app_dir, "uploads")

os.makedirs(server.UPLOADS_DIR, exist_ok=True)
os.makedirs(server.OUTPUTS_DIR, exist_ok=True)

def _open_browser_when_ready(port):
    import time
    time.sleep(1.2)
    url = f"http://127.0.0.1:{port}"
    try:
        webbrowser.open(url)
    except Exception:
        pass

def main():
    port = server.PORT
    threading.Thread(target=_open_browser_when_ready, args=(port,), daemon=True).start()
    server.run(port=port)

if __name__ == '__main__':
    main()
