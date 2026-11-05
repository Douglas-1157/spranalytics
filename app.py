import collections
import hmac
import io
import logging
import math
import os
import re
import threading
import time
import uuid
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

import spr as sg

app = Flask(__name__, static_folder="static", static_url_path="/static")


MAX_UPLOAD = 8 * 1024 * 1024  
MAX_SESSIONS = 20 
MAX_STORE_BYTES = 200 * 1024 * 1024  
TTL = 2 * 3600 
MAX_LEVELS = 8
MAX_SELECTED = 24
MAX_COMPARE = 4
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD

TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if os.environ.get("SPR_BEHIND_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)


STORE = {}
LOCK = threading.Lock()


class UserError(Exception):
    """Mensagem segura para mostrar ao usuário."""


class Limiter:
    """Janela deslizante por chave (IP + tipo de ação), em memória."""

    def __init__(self):
        self.h = {}
        self.lock = threading.Lock()

    def _q(self, key, window, now):
        q = self.h.setdefault(key, collections.deque())
        while q and now - q[0] > window:
            q.popleft()
        return q

    def blocked(self, key, limit, window):
        now = time.time()
        with self.lock:
            q = self._q(key, window, now)
            return (int(window - (now - q[0])) + 1) if len(q) >= limit else 0

    def hit(self, key, limit, window):
        """Registra e devolve 0 se pode, ou segundos de espera se estourou o limite."""
        now = time.time()
        with self.lock:
            q = self._q(key, window, now)
            if len(q) >= limit:
                return int(window - (now - q[0])) + 1
            q.append(now)
            if len(self.h) > 5000:
                for k in [k for k, v in self.h.items() if not v or now - v[-1] > 3600]:
                    self.h.pop(k, None)
            return 0

    def record(self, key, window):
        now = time.time()
        with self.lock:
            self._q(key, window, now).append(now)


RATE = Limiter()
FAILS = Limiter()



def _purge(extra=0):
    now = time.time()
    for k in [k for k, v in STORE.items() if now - v["t"] > TTL]:
        STORE.pop(k, None)
    while STORE and (
        len(STORE) >= MAX_SESSIONS or sum(v["size"] for v in STORE.values()) + extra > MAX_STORE_BYTES
    ):
        STORE.pop(min(STORE, key=lambda k: STORE[k]["t"]), None)


def _entry(token):
    if not isinstance(token, str) or not TOKEN_RE.match(token):
        raise UserError("A sessão expirou. Envie o arquivo CSV de novo.")
    with LOCK:
        e = STORE.get(token)
        if not e:
            raise UserError("A sessão expirou. Envie o arquivo CSV de novo.")
        e["t"] = time.time()
        return e


def _channels(token, metric):
    if not isinstance(metric, str) or not metric or len(metric) > 80:
        raise UserError("Medida inválida.")
    e = _entry(token)
    cache = e["cache"]
    if metric in cache:
        return cache[metric]
    with e["lock"]:  
        if metric not in cache:
            cache[metric] = sg.read_channels(e["data"], metric)
        return cache[metric]



def _levels(raw):
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_LEVELS:
        raise UserError(f"Use no máximo {MAX_LEVELS} níveis.")
    out = []
    for l in raw:
        if not isinstance(l, dict):
            raise UserError("Nível inválido.")
        label = sg.clean_text(l.get("label") or "Nível", 40) or "Nível"
        try:
            a = float(str(l.get("start")).replace(",", "."))
            b = float(str(l.get("end")).replace(",", "."))
        except ValueError:
            raise UserError("Preencha início e fim de cada nível com números.")
        if not (math.isfinite(a) and math.isfinite(b)) or a < 0 or b > 1e5:
            raise UserError(f"No “{label}”, use valores de tempo válidos (em minutos).")
        if b <= a:
            raise UserError(f"No “{label}”, o fim precisa ser maior que o início.")
        out.append(sg.Level(label, a, b))
    return out


def _selected(raw, chans):
    if not raw:
        return [c.name for c in chans]
    if not isinstance(raw, list) or len(raw) > MAX_SELECTED or not all(isinstance(x, str) for x in raw):
        raise UserError("Seleção de canais inválida.")
    return raw


def _pair(raw, n_levels):
    if not raw:
        return None
    if (
        not isinstance(raw, (list, tuple))
        or len(raw) != 2
        or not all(type(x) is int for x in raw)
        or raw[0] == raw[1]
        or not all(0 <= x < n_levels for x in raw)
    ):
        raise UserError("A escolha dos níveis do Δ é inválida.")
    return (raw[0], raw[1])


def _compare(raw, chans):
    """Comparação: {"channels": [...2 a 4 nomes], "names": [...legendas]} -> lista de (canal, legenda)."""
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise UserError("Comparação inválida.")
    cs, ns = raw.get("channels"), raw.get("names") or []
    valid = {c.name for c in chans}
    if (
        not isinstance(cs, list)
        or not isinstance(ns, list)
        or not 2 <= len(cs) <= MAX_COMPARE
        or len(set(cs)) != len(cs)
        or not all(isinstance(x, str) and x in valid for x in cs)
        or len(ns) > MAX_COMPARE
        or not all(isinstance(x, str) for x in ns)
    ):
        raise UserError(f"Escolha de 2 a {MAX_COMPARE} canais diferentes para comparar.")
    return [
        (c, sg.clean_text(ns[i]) if i < len(ns) and sg.clean_text(ns[i]) else c) for i, c in enumerate(cs)
    ]


def _json():
    j = request.get_json(silent=True)
    if not isinstance(j, dict):
        raise UserError("Requisição inválida.")
    return j



def _deny(code, msg, retry=None):
    r = jsonify(error=msg)
    r.status_code = code
    if retry:
        r.headers["Retry-After"] = str(retry)
    return r


@app.before_request
def _gate():
    if request.path == "/healthz":
        return None
    ip = request.remote_addr or "?"

   
    if request.method == "POST":
        origin = request.headers.get("Origin")
        if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
            origin and urlparse(origin).netloc != request.host
        ):
            app.logger.warning("pedido de origem cruzada recusado ip=%s origin=%s", ip, origin)
            return _deny(403, "Origem não permitida.")

   
    pwd = os.environ.get("SPR_PASSWORD")
    if pwd:
        wait = FAILS.blocked(ip, 10, 300)
        if wait:
            return _deny(429, "Muitas tentativas de senha. Aguarde alguns minutos.", wait)
        got = request.authorization
        if not (got and got.password and hmac.compare_digest(got.password.encode(), pwd.encode())):
            if got:
                FAILS.record(ip, 300)
                app.logger.warning("senha incorreta ip=%s", ip)
            return Response("Acesso restrito.", 401, {"WWW-Authenticate": 'Basic realm="SprAnalytics"'})

   
    if request.path.startswith("/api/"):
        limits = {"/api/upload": (20, 600), "/api/generate": (30, 60)}
        limit, window = limits.get(request.path, (300, 60))
        wait = RATE.hit(f"{ip}:{request.path}", limit, window)
        if wait:
            return _deny(429, "Muitas requisições. Aguarde um instante e tente de novo.", wait)
    return None


@app.after_request
def _headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store" 
    if request.is_secure:
        resp.headers["Strict-Transport-Security"] = "max-age=15552000"
    return resp



@app.errorhandler(UserError)
@app.errorhandler(sg.InputError)
def _user_error(e):
    return jsonify(error=str(e)), 400


@app.errorhandler(413)
def _too_big(e):
    return jsonify(error=f"Arquivo grande demais (limite de {MAX_UPLOAD // 2**20} MB)."), 413


@app.errorhandler(ModuleNotFoundError)
def _missing_module(e):
    nome = (getattr(e, "name", "") or "um componente").split(".")[0]
    return (
        jsonify(
            error=f"Falta instalar o componente “{nome}” neste computador. Feche o site, dê dois cliques em "
            f"iniciar.bat (ele instala tudo sozinho) e tente de novo."
        ),
        500,
    )


@app.errorhandler(Exception)
def _any_error(e):
    from werkzeug.exceptions import HTTPException

    if isinstance(e, HTTPException):
        return jsonify(error=e.name), e.code
    app.logger.exception("erro inesperado")  
    return (
        jsonify(
            error="Algo deu errado ao processar. Confira se o arquivo é o CSV do Sensorgrama e tente de novo."
        ),
        500,
    )



@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/api/upload")
def upload():
    f = request.files.get("csv")
    if not f:
        raise UserError("Envie um arquivo CSV.")
    name = sg.clean_text(os.path.basename((f.filename or "").replace("\\", "/")), 80) or "arquivo.csv"
    if not name.lower().endswith((".csv", ".txt")):
        raise UserError("Envie um arquivo .csv exportado pelo Sensorgrama.")
    data = f.read()
    try:
        metrics = sg.list_metrics(data)
        metric = "PeakMinAngle" if "PeakMinAngle" in metrics else metrics[0]
        chans = sg.read_channels(data, metric)
    except sg.InputError:
        raise
    except Exception:
        app.logger.exception("falha ao ler CSV")
        raise UserError("Não consegui ler esse CSV. Confira se é o arquivo exportado pelo Sensorgrama.")
    size = len(data) * 4  
    token = uuid.uuid4().hex
    with LOCK:
        _purge(size)
        STORE[token] = {
            "t": time.time(),
            "data": data,
            "size": size,
            "lock": threading.Lock(),
            "cache": {metric: chans},
        }
    app.logger.info("upload ok ip=%s bytes=%d canais=%d", request.remote_addr, len(data), len(chans))
    return jsonify(
        token=token,
        name=name,
        metrics=metrics,
        metric=metric,
        channels=[c.name for c in chans],
        points=len(chans[0].x),
    )


@app.post("/api/channels")
def channels():
    j = _json()
    chans = _channels(j.get("token"), j.get("metric"))
    return jsonify(channels=[c.name for c in chans], points=len(chans[0].x))


@app.post("/api/detect")
def detect():
    j = _json()
    chans = _channels(j.get("token"), j.get("metric"))
    sel = j.get("channels") or []
    if not isinstance(sel, list) or not all(isinstance(x, str) for x in sel):
        raise UserError("Seleção de canais inválida.")
    chans = [c for c in chans if not sel or c.name in sel]
    lv = sg.detect_levels_multi(chans)
    return jsonify(levels=[{"label": l.label, "start": l.start, "end": l.end} for l in lv])


@app.post("/api/preview")
def preview():
    j = _json()
    chans = _channels(j.get("token"), j.get("metric"))
    cmp = _compare(j.get("compare"), chans)
    if cmp:
        png, _, _ = sg.convert_compare_chart(
            _entry(j.get("token"))["data"], j.get("metric"), cmp, _levels(j.get("levels")), "png", dpi=110
        )
        return send_file(io.BytesIO(png), mimetype="image/png")
    ch = next((c for c in chans if c.name == j.get("channel")), chans[0])
    png = sg.render_chart(ch, _levels(j.get("levels")), "png", shade=True, dpi=110)
    return send_file(io.BytesIO(png), mimetype="image/png")


@app.post("/api/generate")
def generate():
    j = _json()
    metric = j.get("metric")
    chans = _channels(j.get("token"), metric)
    selected = _selected(j.get("channels"), chans)
    levels = _levels(j.get("levels"))
    fmt = j.get("format", "xlsx")
    if fmt not in ("xlsx", "png", "jpg", "pdf"):
        raise UserError("Formato inválido.")
    data = _entry(j.get("token"))["data"]
    cmp = _compare(j.get("compare"), chans)
    if cmp and fmt != "xlsx":
        out, mime, name = sg.convert_compare_chart(data, metric, cmp, levels, fmt)
        return send_file(io.BytesIO(out), as_attachment=True, download_name=name, mimetype=mime)
    if fmt == "xlsx":
        out = sg.convert(data, metric, selected, levels, _pair(j.get("pair"), len(levels)), cmp)
        return send_file(
            io.BytesIO(out),
            as_attachment=True,
            download_name=f"SprAnalytics_{sg.safe_name(metric)}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    out, mime, name = sg.convert_charts(data, metric, selected, levels, fmt)
    return send_file(io.BytesIO(out), as_attachment=True, download_name=name, mimetype=mime)



def _check_deps():
    faltam = []
    for mod, pkg in (
        ("flask", "flask"),
        ("openpyxl", "openpyxl"),
        ("matplotlib", "matplotlib"),
        ("PIL", "pillow"),
    ):
        try:
            __import__(mod)
        except ImportError:
            faltam.append(pkg)
    if faltam:
        print("\n" + "=" * 60)
        print("ATENÇÃO: faltam componentes:", ", ".join(faltam))
        print("Rode:  pip install -r requirements.txt   (ou dê dois cliques em iniciar.bat)")
        print("O Excel pode funcionar sem eles, mas imagem/PDF não.")
        print("=" * 60 + "\n")


if os.environ.get("SPR_BEHIND_PROXY") == "1" and not os.environ.get("SPR_PASSWORD"):
    app.logger.warning(
        "AVISO: o site está público e SEM senha. Defina SPR_PASSWORD para restringir o acesso."
    )


if __name__ == "__main__":
    _check_deps()
    print("SprAnalytics rodando em http://localhost:5000  (Ctrl+C para fechar)")
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)), threaded=True)
