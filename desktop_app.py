import os
import sys
import time
import threading
import urllib.request
import uvicorn

# Ensure backend directory is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

def start_backend():
    from app import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

def wait_for_server(url="http://127.0.0.1:8000/api/status", timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False

def main():
    print("=" * 60)
    print("  Starting IMD SYNOP Desktop Web Application...")
    print("  Ingestion: AMSS Delhi Live (https://amssdelhi.gov.in)")
    print("=" * 60)

    # 1. Start backend in daemon thread
    server_thread = threading.Thread(target=start_backend, daemon=True)
    server_thread.start()

    # 2. Wait for server to become ready
    if not wait_for_server():
        print("Warning: Backend took longer than expected to start.")

    app_url = "http://127.0.0.1:8000"

    # 3. Launch native desktop window via pywebview
    try:
        import webview
        print("Launching native desktop window (pywebview / WebView2)...")
        window = webview.create_window(
            title="IMD SYNOP Monitor & SLA Tracker",
            url=app_url,
            width=1280,
            height=840,
            min_size=(960, 600),
            background_color="#000000"
        )
        webview.start()
    except Exception as e:
        print(f"Native webview fallback due to: {e}")
        # Fallback to Windows Edge App Mode (Dedicated desktop window)
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if os.path.exists(edge_path):
            import subprocess
            cmd = [edge_path, f"--app={app_url}", "--window-size=1280,840"]
            subprocess.run(cmd)
        else:
            import webbrowser
            webbrowser.open(app_url)

if __name__ == "__main__":
    main()
