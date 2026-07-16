import ast
import base64
import datetime
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
import urllib.parse
import urllib.request

SENSITIVE_TOOLS = {"run_code", "write_file", "send_email", "upload_file", "github_create_issue"}

SYSTEM_PROMPT = (
    "You are Veronica AI, an advanced terminal assistant with extensive tool access. "
    "You can read/write files (read_file, write_file, list_dir), run and review Python code "
    "(run_code, review_code), search the web (web_search), get weather (get_weather), "
    "fetch URLs (read_url), make HTTP requests (http_request), manage GitHub repos "
    "(github_get_repo, github_list_issues, github_create_issue, github_search_code), "
    "send emails with attachments (send_email), and upload files (upload_file). "
    "Keep replies concise and in the user's language. "
    "When you have the answer from a tool, summarize it clearly."
)


def _fetch(url, extra_headers=None):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")


def _strip(html):
    return re.sub(r"<.*?>", "", html).strip()


def _ddg(query, num):
    html = _fetch("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query) + "&kl=id-id")
    blocks = re.findall(
        r'class="result__a"[^>]*href="([^"]+)".*?>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.S,
    )
    out = []
    for link, title, snippet in blocks:
        link = urllib.parse.unquote(link)
        if link.startswith("//"):
            link = "https:" + link
        out.append((_strip(title), link, _strip(snippet)))
        if len(out) >= num:
            break
    return out


def _decode_bing_url(href):
    m = re.search(r"u=a1([^&]+)", href)
    if not m:
        return href
    try:
        return base64.b64decode(m.group(1) + "==").decode("utf-8", "ignore")
    except Exception:
        return href


def _bing(query, num):
    html = _fetch("https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&setlang=id&cc=ID")
    blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', html, re.S)
    out = []
    for block in blocks:
        tm = re.search(r'<h2[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not tm:
            continue
        sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        out.append((_strip(tm.group(2)), _decode_bing_url(tm.group(1)), _strip(sm.group(1)) if sm else ""))
        if len(out) >= num:
            break
    return out


def _google(query, num):
    html = _fetch("https://www.google.com/search?q=" + urllib.parse.quote(query) + "&hl=id&gl=ID&cr=countryID",
                  {"Accept-Language": "id-ID,id;q=0.9"})
    out = []
    for m in re.finditer(
        r'<div class="g"[^>]*>.*?<h3[^>]*>(.*?)</h3>.*?<a href="(https?://[^"]+)".*?<div[^>]*>(.*?)</div>',
        html,
        re.S,
    ):
        title, link, snippet = _strip(m.group(1)), m.group(2), _strip(m.group(3))
        if "google" in link or "http" not in link:
            continue
        out.append((title, link, snippet))
        if len(out) >= num:
            break
    return out


def web_search(query, num_results=5):
    last_err = ""
    for backend in (_ddg, _bing, _google):
        try:
            results = backend(query, num_results)
        except Exception as exc:
            last_err = str(exc)
            continue
        if results:
            lines = [f"{i}. {t}\n   {u}\n   {s}" for i, (t, u, s) in enumerate(results, 1)]
            return "\n\n".join(lines)
        last_err = "no results"

    return f"[web_search failed: {last_err}]"


def get_current_time(timezone=None):
    now = datetime.datetime.now()
    return now.strftime("Current local time: %Y-%m-%d %H:%M:%S")


def calculate(expression):
    try:
        node = ast.parse(expression, mode="eval")
        for n in ast.walk(node):
            if not isinstance(n, (ast.Expression, ast.Constant, ast.BinOp,
                                  ast.UnaryOp, ast.Num, ast.Name, ast.Load,
                                  ast.Add, ast.Sub, ast.Mult, ast.Div,
                                  ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd)):
                return "[calculate error: only arithmetic allowed]"
        return str(eval(compile(node, "<calc>", "eval")))
    except Exception as exc:
        return f"[calculate error: {exc}]"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information, news, or facts. Returns result titles, URLs and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Return the current local date and time.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a basic arithmetic expression, e.g. '23 * 47 + 12'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Arithmetic expression"}
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather conditions for a location using wttr.in.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name or location"}
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": "Fetch a URL and return its page title and text content (up to 3000 chars).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full URL to fetch"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the filesystem and return its text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (absolute or relative to cwd)"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write text content to a file. New directories are created automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write to"},
                    "content": {"type": "string", "description": "Text content to write"}
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at a given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default: current directory)"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_code",
            "description": "Execute Python code and return its output. Will ask for user confirmation first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"}
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "review_code",
            "description": "Analyze Python code for syntax errors, style issues, and potential problems.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to review"}
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": "Make an HTTP request to any REST API. Auto-injects GitHub token for api.github.com.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL (including https://)"},
                    "method": {"type": "string", "description": "HTTP method: GET, POST, PUT, DELETE, PATCH"},
                    "headers": {"type": "object", "description": "Optional headers as key/value pairs"},
                    "body": {"type": "string", "description": "Request body (string or JSON dict)"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_repo",
            "description": "Get details about a GitHub repository (owner, stars, forks, language, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository name as 'owner/repo' or just 'repo' (defaults to FaqihAbdulMaalik org)"}
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_issues",
            "description": "List GitHub issues for a repository, optionally filtered by state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository name as 'owner/repo'"},
                    "state": {"type": "string", "description": "Issue state: open, closed, all (default: open)"}
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_create_issue",
            "description": "Create a new GitHub issue. Will ask for confirmation first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository name as 'owner/repo'"},
                    "title": {"type": "string", "description": "Issue title"},
                    "body": {"type": "string", "description": "Issue body/description"}
                },
                "required": ["repo", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_search_code",
            "description": "Search GitHub for code matching a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (supports language:python, repo:, etc.)"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email via SMTP. Supports optional file attachments. Will ask for confirmation first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body text"},
                    "attachment_path": {"type": "string", "description": "Optional path to a file to attach"}
                },
                "required": ["to", "subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_file",
            "description": "Upload a file to transfer.sh (public, expires in 14 days). Returns a shareable URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to upload"}
                },
                "required": ["path"],
            },
        },
    },
]


def get_weather(location):
    url = "https://wttr.in/" + urllib.parse.quote(location) + "?format=%C+%t+%h+%w&lang=id"
    try:
        return _fetch(url).strip()
    except Exception as exc:
        return f"[weather error: {exc}]"


def read_url(url):
    try:
        html = _fetch(url)
        title_m = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
        title = _strip(title_m.group(1)) if title_m else ""
        body_m = re.search(r'<body[^>]*>(.*?)</body>', html, re.I | re.S)
        body = _strip(body_m.group(1)) if body_m else _strip(html)
        body = re.sub(r'\s+', ' ', body)[:3000]
        return f"Title: {title}\n\n{body}" if title else body[:3000]
    except Exception as exc:
        return f"[read_url error: {exc}]"


def read_file(path):
    abs_path = os.path.abspath(os.path.join(os.getcwd(), path))
    if not os.path.exists(abs_path):
        return f"[read_file error: file not found]"
    if os.path.isdir(abs_path):
        return f"[read_file error: path is a directory, use list_dir instead]"
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return content[:20000]
    except Exception as exc:
        return f"[read_file error: {exc}]"


def write_file(path, content):
    abs_path = os.path.abspath(os.path.join(os.getcwd(), path))
    dir_path = os.path.dirname(abs_path)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[written {len(content)} bytes to {abs_path}]"
    except Exception as exc:
        return f"[write_file error: {exc}]"


def list_dir(path="."):
    abs_path = os.path.abspath(os.path.join(os.getcwd(), path))
    if not os.path.exists(abs_path):
        return f"[list_dir error: path not found]"
    if not os.path.isdir(abs_path):
        return f"[list_dir error: not a directory]"
    try:
        items = os.listdir(abs_path)
        lines = []
        for name in sorted(items):
            full = os.path.join(abs_path, name)
            suffix = "/" if os.path.isdir(full) else ""
            size = os.path.getsize(full) if os.path.isfile(full) else 0
            size_str = f" ({size} B)" if size else ""
            lines.append(f"  {name}{suffix}{size_str}")
        return f"Contents of {abs_path}:\n" + "\n".join(lines)
    except Exception as exc:
        return f"[list_dir error: {exc}]"


def run_code(code, timeout=15):
    import subprocess as _subprocess
    import tempfile as _tempfile
    try:
        with _tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            tmppath = f.name
        try:
            r = _subprocess.run(
                [sys.executable, tmppath],
                capture_output=True, text=True, timeout=timeout,
            )
            out = r.stdout
            err = r.stderr
        except _subprocess.TimeoutExpired:
            return "[run_code error: execution timed out]"
        finally:
            try:
                os.unlink(tmppath)
            except OSError:
                pass
        if r.returncode != 0:
            return (out or "") + (err or "")
        return out or "[code executed successfully, no output]"
    except Exception as exc:
        return f"[run_code error: {exc}]"


def review_code(code):
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"[syntax error]\n{exc}"
    lines = code.split("\n")
    issues = []

    func_count = 0
    class_count = 0
    import_count = 0
    todo_count = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("# TODO") or stripped.startswith("# TODO") or stripped.startswith("#FIXME"):
            todo_count += 1
            issues.append(f"Line {i}: TODO/FIXME comment")

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_count += 1
            if len(node.body) > 50:
                issues.append(f"Line {node.lineno}: Function '{node.name}' has {len(node.body)} body lines (aim for < 50)")
            if not node.name.islower():
                issues.append(f"Line {node.lineno}: Function '{node.name}' should use snake_case")
            if not node.body:
                issues.append(f"Line {node.lineno}: Empty function '{node.name}'")
            if node.name.startswith("__") and node.name.endswith("__"):
                if node.name not in ("__init__", "__str__", "__repr__", "__len__", "__iter__", "__next__", "__enter__", "__exit__", "__call__", "__getitem__", "__setitem__", "__contains__", "__bool__"):
                    issues.append(f"Line {node.lineno}: Unusual dunder method '{node.name}'")
        elif isinstance(node, ast.AsyncFunctionDef):
            func_count += 1
        elif isinstance(node, ast.ClassDef):
            class_count += 1
            if not node.bases and "Exception" not in str(node.name):
                if node.name not in ("object",):
                    issues.append(f"Line {node.lineno}: Class '{node.name}' has no base class")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            import_count += 1
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                issues.append(f"Line {node.lineno}: __future__ import (usually unnecessary)")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr in ("eval", "exec", "__import__", "compile"):
                issues.append(f"Line {node.lineno}: Avoid {fn.attr}() — potential security risk")
            if isinstance(fn, ast.Name) and fn.id in ("input",):
                issues.append(f"Line {node.lineno}: input() used — may block execution")
        elif isinstance(node, ast.Try) and not node.handlers and not node.finalbody:
            issues.append(f"Line {node.lineno}: Bare try without except or finally")
        elif isinstance(node, ast.Global):
            issues.append(f"Line {node.lineno}: Avoid global variables")
        elif isinstance(node, ast.Assert):
            issues.append(f"Line {node.lineno}: assert used (ignored with -O flag)")

    summary = [f"Analyzed {len(lines)} lines:"]
    summary.append(f"  Functions: {func_count}, Classes: {class_count}, Imports: {import_count}")
    if todo_count:
        summary.append(f"  TODOs: {todo_count}")
    if not issues and todo_count:
        return "\n".join(summary + [f"  {todo_count} TODO(s) found"])
    if not issues:
        return "\n".join(summary + ["  No issues found."])
    return "\n".join([*summary, *issues])


def http_request(method="GET", url="", headers=None, body=None):
    extra_headers = dict(headers or {})
    if "api.github.com" in url:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token and "Authorization" not in extra_headers:
            extra_headers["Authorization"] = f"Bearer {token}"
    data = None
    if body:
        if isinstance(body, dict) or (isinstance(body, str) and body.strip().startswith("{")):
            if isinstance(body, str):
                body = json.loads(body)
            data = json.dumps(body).encode()
            extra_headers.setdefault("Content-Type", "application/json")
        else:
            data = body.encode() if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method=method.upper() if method else "GET")
    req.add_header("User-Agent", "terminal-chatbot/2.0")
    for k, v in extra_headers.items():
        req.add_header(k, v)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        resp_body = resp.read().decode("utf-8", "ignore")
        return f"Status: {resp.status}\n\n{resp_body[:5000]}"
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:1000]}"
    except Exception as exc:
        return f"[http_request error: {exc}]"


def _github_auth():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _github_repo(repo):
    return repo if "/" in repo else f"FaqihAbdulMaalik/{repo}"


def github_get_repo(repo):
    return http_request("GET", f"https://api.github.com/repos/{_github_repo(repo)}")


def github_list_issues(repo, state="open"):
    return http_request("GET", f"https://api.github.com/repos/{_github_repo(repo)}/issues?state={state}&per_page=20")


def github_create_issue(repo, title, body=""):
    return http_request("POST", f"https://api.github.com/repos/{_github_repo(repo)}/issues", body={"title": title, "body": body})


def github_search_code(query):
    return http_request("GET", f"https://api.github.com/search/code?q={urllib.parse.quote(query)}")


def send_email(to, subject, body="", attachment_path=None, smtp_server=None, smtp_port=None, smtp_user=None, smtp_pass=None):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders

    server = smtp_server or os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    port = smtp_port or int(os.environ.get("SMTP_PORT", "587"))
    user = smtp_user or os.environ.get("SMTP_USER")
    password = smtp_pass or os.environ.get("SMTP_PASS")
    from_addr = os.environ.get("EMAIL_FROM") or user

    if not all([server, user, password]):
        return "[send_email error: SMTP not configured. Set SMTP_SERVER, SMTP_USER, SMTP_PASS in .env]"

    if attachment_path and os.path.exists(attachment_path):
        msg = MIMEMultipart()
        msg.attach(MIMEText(body or ""))
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            filename = os.path.basename(attachment_path)
            part.add_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
            msg.attach(part)
    else:
        msg = MIMEText(body or "")

    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to

    try:
        with smtplib.SMTP(server, port) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
        return f"[email sent to {to}]"
    except Exception as exc:
        return f"[send_email error: {exc}]"


def upload_file(path):
    abs_path = os.path.abspath(os.path.join(os.getcwd(), path))
    if not os.path.isfile(abs_path):
        return f"[upload_file error: file not found]"
    try:
        with open(abs_path, "rb") as f:
            data = f.read()
        filename = os.path.basename(abs_path)
        req = urllib.request.Request(
            f"https://transfer.sh/{urllib.parse.quote(filename)}",
            data=data,
            method="PUT",
            headers={"User-Agent": "terminal-chatbot/2.0"},
        )
        resp = urllib.request.urlopen(req, timeout=60)
        url = resp.read().decode().strip()
        return f"[uploaded to {url}]"
    except Exception as exc:
        return f"[upload_file error: {exc}]"


DISPATCH = {
    "web_search": lambda args: web_search(args.get("query", "")),
    "get_current_time": lambda args: get_current_time(),
    "calculate": lambda args: calculate(args.get("expression", "")),
    "get_weather": lambda args: get_weather(args.get("location", "")),
    "read_url": lambda args: read_url(args.get("url", "")),
    "read_file": lambda args: read_file(args.get("path", "")),
    "write_file": lambda args: write_file(args.get("path", ""), args.get("content", "")),
    "list_dir": lambda args: list_dir(args.get("path", ".")),
    "run_code": lambda args: run_code(args.get("code", "")),
    "review_code": lambda args: review_code(args.get("code", "")),
    "http_request": lambda args: http_request(
        args.get("method", "GET"),
        args.get("url", ""),
        args.get("headers"),
        args.get("body"),
    ),
    "github_get_repo": lambda args: github_get_repo(args.get("repo", "")),
    "github_list_issues": lambda args: github_list_issues(args.get("repo", ""), args.get("state", "open")),
    "github_create_issue": lambda args: github_create_issue(args.get("repo", ""), args.get("title", ""), args.get("body", "")),
    "github_search_code": lambda args: github_search_code(args.get("query", "")),
    "send_email": lambda args: send_email(args.get("to", ""), args.get("subject", ""), args.get("body", ""), args.get("attachment_path")),
    "upload_file": lambda args: upload_file(args.get("path", "")),
}


def execute_tool(name, args):
    fn = DISPATCH.get(name)
    if not fn:
        return f"[unknown tool: {name}]"
    try:
        return str(fn(args))
    except Exception as exc:
        return f"[tool {name} error: {exc}]"
