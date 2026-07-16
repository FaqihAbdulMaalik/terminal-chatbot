import json
import os
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from terminal_chatbot.config import build_provider, PROVIDERS
from terminal_chatbot.tools import TOOLS, SYSTEM_PROMPT, execute_tool


def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


class VeronicaAPI(BaseHTTPRequestHandler):

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length).decode()) if length else {}

    def _build_history(self, messages):
        sys_prompt = SYSTEM_PROMPT
        msgs = []
        for msg in messages:
            if msg["role"] == "system":
                sys_prompt = msg["content"]
            else:
                msgs.append(msg)
        return [{"role": "system", "content": sys_prompt}] + msgs

    def _run_agent(self, history, model):
        provider = build_provider("opencode", model=model)
        max_rounds = 4
        rounds = 0
        while True:
            message = provider.chat(history, tools=TOOLS)
            if message.get("tool_calls"):
                rounds += 1
                if rounds > max_rounds:
                    history.append({"role": "user", "content": "Stop using tools. Answer now."})
                    continue
                history.append(message)
                for call in message["tool_calls"]:
                    name = call["function"]["name"]
                    try:
                        args = json.loads(call["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = execute_tool(name, args)
                    history.append({"role": "tool", "content": result, "tool_call_id": call["id"]})
                continue
            return message.get("content") or ""

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/v1/models":
            models = []
            for pid, spec in PROVIDERS.items():
                for m in spec["models"]:
                    models.append({
                        "id": m,
                        "object": "model",
                        "owned_by": pid,
                        "permission": [],
                    })
            self._send_json(200, {
                "object": "list",
                "data": models,
            })
        elif path == "/health":
            self._send_json(200, {"status": "ok", "provider": "veronica"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/v1/chat/completions":
            self._handle_chat()
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_chat(self):
        try:
            body = self._read_body()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_json(400, {"error": f"invalid JSON: {exc}"})
            return

        model = body.get("model", "hy3-free")
        messages = body.get("messages", [])
        stream = body.get("stream", False)

        if not messages:
            self._send_json(400, {"error": "messages required"})
            return

        history = self._build_history(messages)
        response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                content = self._run_agent(history, model)
                for char in content:
                    chunk = {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": char}, "finish_reason": None}],
                    }
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    self.wfile.flush()
                final = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception as exc:
                err = {"id": response_id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}]}
                self.wfile.write(f"data: {json.dumps(err)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
        else:
            try:
                content = self._run_agent(history, model)
                self._send_json(200, {
                    "id": response_id,
                    "object": "chat.completion",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                })
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})

    def log_message(self, format, *args):
        method, path, code = args[0], args[1], args[2]
        print(f"  [{method}] {path} → {code}")


def main():
    import argparse
    load_env()
    p = argparse.ArgumentParser(description="Veronica AI API server (OpenAI-compatible)")
    p.add_argument("--host", default="127.0.0.1", help="bind address")
    p.add_argument("--port", type=int, default=8080, help="bind port")
    args = p.parse_args()
    server = HTTPServer((args.host, args.port), VeronicaAPI)
    print(f"Veronica AI API running at http://{args.host}:{args.port}")
    print(f"  POST /v1/chat/completions  (OpenAI-compatible)")
    print(f"  GET  /v1/models")
    print(f"  GET  /health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
