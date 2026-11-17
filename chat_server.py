"""Offline chat page for local Llama 3.2.

The browser talks to this server. This server streams the reply from Ollama.
Both stay on this PC:

    browser -> http://127.0.0.1:8765 -> http://127.0.0.1:11434

No API key, no cloud model, no extra packages.

Usage:
    python chat_server.py
    python chat_server.py --cli
    python chat_server.py --once "What is 2 + 2?"
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434"
CHAT_HOST = "127.0.0.1"
CHAT_PORT = 8765
MODEL = "llama3.2:latest"
DISPLAY_MODEL = "llama3.2:3b"
STATIC_DIR = Path(__file__).resolve().parent / "static"

SYSTEM_PROMPT = (
    "You are a helpful assistant running on this computer. "
    "Answer the user's question directly."
)

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def ollama_request(path: str, payload: dict | None = None) -> urllib.request.Request:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    return urllib.request.Request(
        f"{OLLAMA_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )


def local_model_installed() -> bool:
    try:
        with urllib.request.urlopen(ollama_request("/api/tags"), timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False
    names = {item.get("name", "") for item in body.get("models", [])}
    base = MODEL.split(":", 1)[0]
    return MODEL in names or base in names or f"{base}:latest" in names


def ensure_local_model() -> None:
    try:
        with urllib.request.urlopen(ollama_request("/api/tags"), timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SystemExit(
            "Ollama is not running on 127.0.0.1:11434.\n"
            "Start the Ollama app, then run this script again."
        ) from exc

    names = {item.get("name", "") for item in body.get("models", [])}
    base = MODEL.split(":", 1)[0]
    if MODEL not in names and base not in names and f"{base}:latest" not in names:
        installed = ", ".join(sorted(names)) or "(none)"
        raise SystemExit(
            f"Model {MODEL!r} is not installed locally.\n"
            f"Installed models: {installed}\n"
            "The weights must already be on disk. This script will not download them."
        )


def stream_reply(messages: list[dict]) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
    }
    request = ollama_request("/api/chat", payload)
    parts: list[str] = []
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise SystemExit(f"\nOllama error: {chunk['error']}")
                token = chunk.get("message", {}).get("content", "")
                if token:
                    parts.append(token)
                    print(token, end="", flush=True)
    except urllib.error.URLError as exc:
        raise SystemExit(f"\nLost connection to local Ollama: {exc}") from exc
    print()
    return "".join(parts)


def chat_loop() -> None:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"Offline chat with {MODEL}", flush=True)
    print("Type a question. Type exit to stop.\n", flush=True)
    while True:
        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            return
        messages.append({"role": "user", "content": user_text})
        print("model> ", end="", flush=True)
        reply = stream_reply(messages)
        messages.append({"role": "assistant", "content": reply})


class ChatHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        request_path = self.path.split("?", 1)[0]
        if request_path == "/api/status":
            ready = local_model_installed()
            body = json.dumps({"ready": ready, "model": DISPLAY_MODEL}).encode("utf-8")
            self._send(200, body, "application/json")
            return
        if request_path == "/":
            request_path = "/index.html"
        relative = request_path.lstrip("/")
        target = (STATIC_DIR / relative).resolve()
        if not target.is_relative_to(STATIC_DIR) or not target.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), content_type)

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/api/chat":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            incoming = json.loads(self.rfile.read(length).decode("utf-8"))
            messages = incoming["messages"]
            if not isinstance(messages, list) or not messages:
                raise ValueError("messages must be a non-empty list")
        except (json.JSONDecodeError, KeyError, ValueError, UnicodeError) as exc:
            self._send(400, str(exc).encode("utf-8"), "text/plain; charset=utf-8")
            return

        payload = {
            "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            "stream": True,
        }
        request = ollama_request("/api/chat", payload)
        try:
            upstream = urllib.request.urlopen(request, timeout=600)
        except urllib.error.URLError as exc:
            detail = f"Cannot reach Ollama on this PC: {exc.reason}".encode("utf-8")
            self._send(502, detail, "text/plain; charset=utf-8")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                chunk = upstream.read(1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        finally:
            upstream.close()


def serve(open_browser: bool) -> None:
    ensure_local_model()
    try:
        server = ThreadingHTTPServer((CHAT_HOST, CHAT_PORT), ChatHandler)
    except OSError as exc:
        raise SystemExit(
            f"Cannot start the chat page on {CHAT_HOST}:{CHAT_PORT} ({exc}).\n"
            "Close the other copy of the chat server and run it again."
        ) from exc

    url = f"http://{CHAT_HOST}:{CHAT_PORT}"
    print(f"Offline chat is running at {url}", flush=True)
    print("Keep this window open. Press Ctrl+C to stop.", flush=True)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline chat with local Llama 3.2.")
    parser.add_argument("--cli", action="store_true", help="Chat in this terminal instead of the browser.")
    parser.add_argument("--once", metavar="PROMPT", help="Ask one question in this terminal and exit.")
    parser.add_argument("--no-browser", action="store_true", help="Start the page without opening a browser.")
    args = parser.parse_args()

    if args.once or args.cli:
        ensure_local_model()
        if args.once:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": args.once},
            ]
            print("model> ", end="", flush=True)
            stream_reply(messages)
            return
        chat_loop()
        return

    serve(open_browser=not args.no_browser)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
