#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
CONFIG_PATH = ROOT / ".odl-webui.json"
HOST = "127.0.0.1"
PORT = int(os.environ.get("ODL_WEBUI_PORT", "8787"))

DEFAULT_CONFIG = {
    "input_dir": "",
    "input_paths": [],
    "output_dir": "",
    "formats": ["markdown", "json"],
    "image_output": "off",
    "use_hybrid_when_running": True,
}

BREW_OPENJDK = Path("/opt/homebrew/opt/openjdk")

daemon_process: subprocess.Popen | None = None
daemon_started_at: float | None = None
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def command_env() -> dict[str, str]:
    env = os.environ.copy()
    if BREW_OPENJDK.exists():
        env["JAVA_HOME"] = str(BREW_OPENJDK)
        env["PATH"] = f"{BREW_OPENJDK / 'bin'}:{env.get('PATH', '')}"
    venv_bin = ROOT / ".venv" / "bin"
    if venv_bin.exists():
        env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
    return env


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return {**DEFAULT_CONFIG, **data}
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def json_response(handler: SimpleHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: SimpleHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def check_dependencies() -> dict:
    env = command_env()
    java = subprocess.run(["java", "-version"], capture_output=True, text=True, env=env)
    pip_show = subprocess.run(
        [sys.executable, "-m", "pip", "show", "opendataloader-pdf"],
        capture_output=True,
        text=True,
        env=env,
    )
    hybrid_bin = shutil.which("opendataloader-pdf-hybrid", path=env.get("PATH"))
    cli_bin = shutil.which("opendataloader-pdf", path=env.get("PATH"))
    return {
        "python": sys.version.split()[0],
        "java_ok": java.returncode == 0,
        "java_output": (java.stderr or java.stdout).strip(),
        "opendataloader_ok": pip_show.returncode == 0,
        "opendataloader_output": pip_show.stdout.strip(),
        "cli_path": cli_bin,
        "hybrid_path": hybrid_bin,
    }


def daemon_state() -> dict:
    global daemon_process
    if daemon_process and daemon_process.poll() is not None:
        daemon_process = None
    return {
        "running": daemon_process is not None,
        "pid": daemon_process.pid if daemon_process else None,
        "started_at": daemon_started_at,
        "port": 5002,
    }


def pick_folder(prompt: str) -> str:
    script = f'POSIX path of (choose folder with prompt "{prompt}")'
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Folder selection canceled.")
    return result.stdout.strip()


def pick_pdfs(prompt: str) -> list[str]:
    script = (
        f'set selectedFiles to choose file with prompt "{prompt}" '
        'of type {"com.adobe.pdf"} with multiple selections allowed\n'
        'set outputPaths to {}\n'
        'repeat with selectedFile in selectedFiles\n'
        '  set end of outputPaths to POSIX path of selectedFile\n'
        'end repeat\n'
        'set AppleScript\'s text item delimiters to linefeed\n'
        'return outputPaths as text'
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PDF selection canceled.")
    return [line for line in result.stdout.splitlines() if line.strip()]


def start_daemon() -> dict:
    global daemon_process, daemon_started_at
    if daemon_process and daemon_process.poll() is None:
        return daemon_state()

    env = command_env()
    hybrid_bin = shutil.which("opendataloader-pdf-hybrid", path=env.get("PATH"))
    if not hybrid_bin:
        raise RuntimeError('未找到 opendataloader-pdf-hybrid。请先运行 ./.venv/bin/pip install "opendataloader-pdf[hybrid]"。')

    log_path = ROOT / "hybrid-daemon.log"
    log_file = log_path.open("a", encoding="utf-8")
    daemon_process = subprocess.Popen(
        [hybrid_bin, "--port", "5002"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        env=env,
        start_new_session=True,
    )
    daemon_started_at = time.time()
    return daemon_state()


def stop_daemon() -> dict:
    global daemon_process, daemon_started_at
    if daemon_process and daemon_process.poll() is None:
        os.killpg(os.getpgid(daemon_process.pid), signal.SIGTERM)
        try:
            daemon_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(daemon_process.pid), signal.SIGKILL)
    daemon_process = None
    daemon_started_at = None
    return daemon_state()


def build_convert_command(config: dict) -> list[str]:
    env = command_env()
    cli_bin = shutil.which("opendataloader-pdf", path=env.get("PATH"))
    if not cli_bin:
        raise RuntimeError("未找到 opendataloader-pdf。请先运行 ./setup.sh。")

    input_paths = config.get("input_paths") or []
    if not input_paths and config.get("input_dir"):
        input_paths = [config["input_dir"]]
    valid_inputs = [path for path in input_paths if Path(path).exists()]
    if not valid_inputs:
        raise RuntimeError("请先选择一个或多个有效的 PDF 文件。")

    output_dir = config.get("output_dir")
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    formats = config.get("formats") or ["markdown"]
    image_output = config.get("image_output") or "off"
    cmd = [cli_bin, *valid_inputs]
    if output_dir:
        cmd += ["-o", output_dir]
    cmd += ["-f", ",".join(formats)]
    if image_output in {"off", "external", "embedded"}:
        cmd += ["--image-output", image_output]

    if config.get("use_hybrid_when_running") and daemon_state()["running"]:
        cmd += ["--hybrid", "docling-fast", "--hybrid-url", "http://127.0.0.1:5002"]

    return cmd


def run_convert_job(job_id: str, config: dict) -> None:
    with jobs_lock:
        jobs[job_id].update({"status": "running", "started_at": time.time()})
    try:
        cmd = build_convert_command(config)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(ROOT),
            env=command_env(),
        )
        output_lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            output_lines.append(line)
            with jobs_lock:
                jobs[job_id]["log"] = "".join(reversed(output_lines[-300:]))
        code = proc.wait()
        with jobs_lock:
            jobs[job_id].update({
                "status": "done" if code == 0 else "failed",
                "returncode": code,
                "finished_at": time.time(),
                "command": " ".join(cmd),
            })
    except Exception as exc:
        with jobs_lock:
            jobs[job_id].update({"status": "failed", "error": str(exc), "finished_at": time.time()})


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        clean_path = parsed.path.lstrip("/") or "index.html"
        return str((WEB_ROOT / clean_path).resolve())

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            json_response(self, {"config": load_config(), "deps": check_dependencies(), "daemon": daemon_state()})
            return
        if parsed.path == "/api/job":
            job_id = parse_qs(parsed.query).get("id", [""])[0]
            with jobs_lock:
                job = jobs.get(job_id)
            json_response(self, {"job": job} if job else {"error": "Job not found."}, 200 if job else 404)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/config":
                config = {**load_config(), **read_json(self)}
                save_config(config)
                json_response(self, {"config": config})
                return
            if parsed.path == "/api/pick-folder":
                payload = read_json(self)
                purpose = payload.get("purpose", "folder")
                prompt = "选择默认输出目录"
                selected = pick_folder(prompt)
                config = load_config()
                config["output_dir"] = selected
                save_config(config)
                json_response(self, {"path": selected, "config": config})
                return
            if parsed.path == "/api/pick-pdfs":
                selected = pick_pdfs("选择一个或多个 PDF 文件")
                config = load_config()
                config["input_paths"] = selected
                config["input_dir"] = ""
                save_config(config)
                json_response(self, {"paths": selected, "config": config})
                return
            if parsed.path == "/api/daemon/start":
                json_response(self, {"daemon": start_daemon()})
                return
            if parsed.path == "/api/daemon/stop":
                json_response(self, {"daemon": stop_daemon()})
                return
            if parsed.path == "/api/shutdown":
                json_response(self, {"message": "WebUI is shutting down."})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if parsed.path == "/api/convert":
                config = load_config()
                job_id = uuid.uuid4().hex[:12]
                with jobs_lock:
                    jobs[job_id] = {"id": job_id, "status": "queued", "log": ""}
                threading.Thread(target=run_convert_job, args=(job_id, config), daemon=True).start()
                json_response(self, {"job_id": job_id})
                return
            json_response(self, {"error": "Not found."}, 404)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)


def main() -> None:
    WEB_ROOT.mkdir(exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG.copy())
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"ODL PDF WebUI running at {url}")
    if os.environ.get("ODL_WEBUI_NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        stop_daemon()


if __name__ == "__main__":
    main()
