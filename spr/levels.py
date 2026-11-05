"""Contas de delta e detecção automática dos níveis (patamares)."""

import math

from .models import Channel, InputError, Level


def _median_filter(a, k=5):
    import statistics

    h = k // 2
    return [statistics.median(a[max(0, i - h) : i + h + 1]) for i in range(len(a))]


def deltas(ch: Channel):
    """tempo (min, zerado) e delta (mdeg) – mesma conta das fórmulas do Excel."""
    t = [x - ch.x[0] for x in ch.x]
    d = [(y - ch.y[0]) * 1000 for y in ch.y]  # equivale ao acumulado (B_n - B_{n-1})*1000
    return t, d


def detect_levels(ch: Channel):
    """Acha os patamares estáveis que vêm DEPOIS de uma queda grande (retorno à linha de base
    após cada injeção). Devolve Level(janela = metade final do patamar)."""
    import statistics

    t, d = deltas(ch)
    n = len(t)
    if n < 30:
        return []
    dt = (t[-1] - t[0]) / (n - 1)
    if not math.isfinite(dt) or dt <= 0:  # tempo parado ou fora de ordem
        return []
    s = _median_filter(d, 5)
    R = max(s) - min(s)
    if R <= 0:
        return []
    noise = statistics.median(abs(d[i + 1] - d[i]) for i in range(n - 1)) * 1.4826 / 1.414
    w = max(3, round(3.0 / dt))  # ~3 min
    thr = max(0.04 * R, 8 * noise)  # tamanho mínimo de um "degrau"
    moving = [abs(s[i + w] - s[i]) > thr for i in range(n - w)]
    fall = [(s[i] - s[i + w]) > thr for i in range(n - w)]
    out, i = [], 0
    while i < n - w:
        if not fall[i]:
            i += 1
            continue
        b = i
        while b + 1 < n - w and fall[b + 1]:
            b += 1
        p0 = min(b + w + 1, n - 1)  # a queda terminou
        end = n - 1
        for j in range(p0, n - w):
            if moving[j]:
                end = j
                break
        if t[end] - t[p0] >= 3.0:
            start_t = t[p0] + 0.5 * (t[end] - t[p0])  # metade final: evita a cauda de relaxamento
            out.append((round(start_t, 2), round(t[end], 2)))
        i = max(end, b + 1)
    return [Level(f"Nível {k + 1}", a, e) for k, (a, e) in enumerate(out)]


def detect_levels_multi(chans):
    """Detecta em cada canal e junta: usa a quantidade de níveis mais comum e a mediana das janelas."""
    import statistics
    from collections import Counter

    per = [p for p in (detect_levels(c) for c in chans) if p]
    if not per:
        return []
    k = Counter(len(p) for p in per).most_common(1)[0][0]
    per = [p for p in per if len(p) == k]
    return [
        Level(
            f"Nível {j + 1}",
            round(statistics.median(p[j].start for p in per), 2),
            round(statistics.median(p[j].end for p in per), 2),
        )
        for j in range(k)
    ]


def level_value(t, d, lv: Level):
    vals = [v for tt, v in zip(t, d) if lv.start <= tt <= lv.end]
    if not vals:
        raise InputError(f"Nível '{lv.label}': nenhum ponto entre {lv.start} e {lv.end} min.")
    return sum(vals) / len(vals)
