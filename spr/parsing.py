"""Leitura do CSV do Sensorgrama e limpeza de textos vindos de fora."""

import csv
import io
import math
import re

from .config import MAX_CHANNELS, MAX_COLS, MAX_ROWS
from .models import Channel, InputError

_CTRL = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]")


def clean_text(s, maxlen=60):
    """Tira caracteres de controle e limita o tamanho (texto vindo do CSV ou digitado no site)."""
    return _CTRL.sub(" ", str(s)).strip()[:maxlen]


def safe_name(s):
    """Nome de arquivo seguro: só letras, números, ponto, hífen e sublinhado (sem '/', '..', espaços)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s)).strip("._") or "arquivo"


# ----------------------------------------------------------------- leitura
def _num(s):
    s = s.strip().replace(" ", "")
    if not s or len(s) > 40:
        return None
    # aceita "68,811256" e "68.811256"; se vier "1.234,56" remove o ponto de milhar
    if "," in s and "." in s:
        s = s.replace(".", "")
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        return None
    return v if math.isfinite(v) else None  # descarta nan/inf


def _reader(data: bytes):
    if b"\x00" in data[:8192]:
        raise InputError("Isso não parece um arquivo CSV de texto.")
    text = data.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") >= first.count(",") else ","
    return csv.reader(io.StringIO(text), delimiter=delim)


def _header(reader):
    try:
        header = next(reader, None)
    except csv.Error:
        raise InputError("Não consegui ler o cabeçalho do CSV.")
    if not header or len(header) > MAX_COLS:
        raise InputError("O CSV não tem o formato esperado do Sensorgrama.")
    return [clean_text(h, 80) for h in header]


def list_metrics(data: bytes):
    """Métricas disponíveis (PeakMinAngle, TirAngle, ...) na ordem do arquivo."""
    out = []
    for h in _header(_reader(data)):
        if h:
            m = h.split(" ", 1)[0]
            if m not in out:
                out.append(m)
    if not out:
        raise InputError("O CSV não tem o formato esperado do Sensorgrama.")
    return out


def read_channels(data: bytes, metric="PeakMinAngle"):
    reader = _reader(data)
    header = _header(reader)
    cols = []  # (índice da coluna x, nome do canal)
    for i, h in enumerate(header[:-1]):
        if not h or " " not in h:
            continue
        m, ch = h.split(" ", 1)
        if m == metric and len(cols) < MAX_CHANNELS:
            cols.append((i, ch.strip()))
    if not cols:
        raise InputError(f"Métrica '{clean_text(metric, 40)}' não encontrada no CSV.")
    xs = [[] for _ in cols]
    ys = [[] for _ in cols]
    n = 0
    try:
        for r in reader:
            n += 1
            if n > MAX_ROWS + 1:
                raise InputError(f"CSV com linhas demais (limite de {MAX_ROWS}).")
            if n == 1 and r and r[0].strip().lower() == "x":  # linha 2 do CSV traz 'x','y'
                continue
            for k, (i, _) in enumerate(cols):
                if len(r) <= i + 1:
                    continue
                x, y = _num(r[i]), _num(r[i + 1])
                if x is None or y is None:
                    continue
                xs[k].append(x)
                ys[k].append(y)
    except csv.Error:
        raise InputError("O CSV está malformado.")
    channels = [Channel(name, xs[k], ys[k]) for k, (_, name) in enumerate(cols) if len(xs[k]) >= 2]
    if not channels:
        raise InputError(f"Não há dados numéricos para '{clean_text(metric, 40)}'.")
    return channels
