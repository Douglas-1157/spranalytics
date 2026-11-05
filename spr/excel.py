"""Geração da planilha Excel (fórmulas + gráficos)."""

import io
import re

from openpyxl import Workbook
from openpyxl.chart import ScatterChart, Reference, Series
from openpyxl.chart.layout import Layout, ManualLayout
from openpyxl.chart.series import SeriesLabel
from openpyxl.chart.data_source import StrRef
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.text import RichText
from openpyxl.drawing.text import CharacterProperties, Paragraph, ParagraphProperties, Font as DFont
from openpyxl.drawing.line import LineProperties
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from .config import COLORS, FIRST_ROW, FONT, SERIES
from .models import Channel, InputError
from .parsing import read_channels

_BAD_SHEET = re.compile(r"[\[\]:*?/\\]")


def _text(cell, value):
    """Grava TEXTO puro. Sem isso, um texto começando com '=' (vindo do CSV ou digitado) viraria fórmula no Excel."""
    cell.value = str(value)
    cell.data_type = "s"
    return cell


def _sheet_title(name, used):
    t = _BAD_SHEET.sub("_", name).strip().strip("'")[:31] or "Canal"
    if t.lower() in used:
        base, k = t[:28], 2
        while f"{base}_{k}".lower() in used:
            k += 1
        t = f"{base}_{k}"
    used.add(t.lower())
    return t


def _qs(name):
    return "'" + name.replace("'", "''") + "'"


def _txt(sz=1000, bold=False, color="404040"):
    cp = CharacterProperties(sz=sz, b=bold, solidFill=color, latin=DFont(typeface=FONT))
    return RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=cp), endParaRPr=cp)])


def _axis_title(chart_axis, text, pos=None):
    from openpyxl.chart.title import Title
    from openpyxl.chart.text import Text
    from openpyxl.drawing.text import RegularTextRun

    cp = CharacterProperties(sz=1200, b=False, solidFill="404040", latin=DFont(typeface="Times New Roman"))
    run = RegularTextRun(rPr=cp, t=text)
    chart_axis.title = Title(
        tx=Text(rich=RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=cp), r=[run])])), overlay=False
    )
    if pos:
        chart_axis.title.layout = Layout(
            manualLayout=ManualLayout(xMode="edge", yMode="edge", x=pos[0], y=pos[1])
        )


def _build_channel_sheet(ws, ch: Channel, levels, metric, pair=None):
    n = len(ch.x)
    last = FIRST_ROW + n - 1
    bold = Font(name=FONT, bold=True)
    base = Font(name=FONT)
    inp = Font(name=FONT, color="0000FF")  # azul = valor de entrada (convenção)

    _text(ws["A1"], f"{metric} {ch.name}")
    ws["A1"].font = bold
    for col, t in zip("ABCD", ["x", "y", "tempo", f"delta_{ch.name.split()[0].lower()}"]):
        ws[f"{col}2"] = t
        ws[f"{col}2"].font = bold
        ws[f"{col}2"].alignment = Alignment(horizontal="center")

    for k in range(n):
        r = FIRST_ROW + k
        ws.cell(r, 1, ch.x[k]).font = inp
        ws.cell(r, 2, ch.y[k]).font = inp
        ws.cell(r, 3, f"=A{r}-$A${FIRST_ROW}").font = base
        if k == 0:
            ws.cell(r, 4, 0).font = base
        else:
            ws.cell(r, 4, f"=(B{r}-B{r-1})*1000+D{r-1}").font = base
        ws.cell(r, 1).number_format = "0.000000"
        ws.cell(r, 2).number_format = "0.000000"
        ws.cell(r, 3).number_format = "0.000"
        ws.cell(r, 4).number_format = "0.000"

    for c, w in zip("ABCD", [12, 14, 10, 12]):
        ws.column_dimensions[c].width = w

    # ---- tabela de níveis (F:I) + pontos auxiliares das linhas (K:L)
    ws["F1"] = "Níveis (média do delta na janela, em min de 'tempo')"
    ws["F1"].font = bold
    for col, t in zip("FGHI", ["Nível", "Início (min)", "Fim (min)", "Δθ (mdeg)"]):
        ws[f"{col}2"] = t
        ws[f"{col}2"].font = bold
        ws[f"{col}2"].alignment = Alignment(horizontal="center")
    ws["K1"] = "Auxiliar das linhas de nível"
    ws["K1"].font = bold
    ws["K2"], ws["L2"], ws["M2"] = "x", "y", "legenda"
    for c in "KLM":
        ws[f"{c}2"].font = bold

    level_rows = []
    for j, lv in enumerate(levels):
        r = 3 + j
        _text(ws[f"F{r}"], lv.label)
        ws[f"G{r}"] = lv.start
        ws[f"H{r}"] = lv.end
        for c in "FGH":
            ws[f"{c}{r}"].font = inp
        ws[f"I{r}"] = (
            f'=AVERAGEIFS($D${FIRST_ROW}:$D${last},$C${FIRST_ROW}:$C${last},">="&G{r},$C${FIRST_ROW}:$C${last},"<="&H{r})'
        )
        ws[f"I{r}"].number_format = "0.000"
        ws[f"I{r}"].font = base
        # duas pontas da linha horizontal (0 .. tempo final)
        a, b = 3 + 2 * j, 4 + 2 * j
        ws[f"K{a}"], ws[f"K{b}"] = 0, f"=MAX($C${FIRST_ROW}:$C${last})"
        ws[f"L{a}"], ws[f"L{b}"] = f"=I{r}", f"=I{r}"
        # FIXED() segue o idioma do Excel (23,853 em português / 23.853 em inglês). TEXT(...,"0.000") NÃO serve:
        # em português o "." do formato vira separador de milhar e 23,853 aparece como "0.024".
        ws[f"M{a}"] = f'=FIXED(I{r},3,TRUE)&" mdeg"'
        level_rows.append((a, b))
        for c in "KLM":
            ws[f"{c}{a}"].font = base
            ws[f"{c}{b}"].font = base

    ws["F11"] = "Δ final (mdeg)"
    ws["I11"] = f"=D{last}"
    ws["F11"].font = bold
    ws["I11"].font = base
    ws["I11"].number_format = "0.000"
    if pair and len(levels) > max(pair):
        a, b = pair
        _text(ws["F12"], f"Δ {levels[b].label} − {levels[a].label} (mdeg)")
        ws["F12"].font = bold
        ws["I12"] = f"=I{3 + b}-I{3 + a}"
        ws["I12"].font = base
        ws["I12"].number_format = "0.000"
    ws["F13"] = "Azul = valor de entrada (pode editar). Preto = fórmula."
    ws["F13"].font = Font(name=FONT, italic=True, color="595959")
    for c, w in zip("FGHIJKLM", [20, 13, 11, 12, 3, 8, 10, 16]):
        ws.column_dimensions[c].width = w

    # ---- gráfico
    chart = ScatterChart()
    chart.style = 2
    chart.scatterStyle = "lineMarker"
    chart.varyColors = False  # sem isso o Excel lista cada ponto na legenda quando há 1 série só
    chart.height, chart.width = 12, 18
    chart.legend.position = "b"
    chart.legend.txPr = _txt(1100)

    xs = Reference(ws, min_col=3, min_row=FIRST_ROW, max_row=last)
    ys = Reference(ws, min_col=4, min_row=FIRST_ROW, max_row=last)
    s = Series(ys, xs)
    s.tx = SeriesLabel(v=ch.name)
    s.marker.symbol = "none"
    s.smooth = False
    s.graphicalProperties = GraphicalProperties(ln=LineProperties(solidFill="1A5F82", w=38100))
    chart.series.append(s)

    for j, (a, b) in enumerate(level_rows):
        ls = Series(
            Reference(ws, min_col=12, min_row=a, max_row=b), Reference(ws, min_col=11, min_row=a, max_row=b)
        )
        ls.tx = SeriesLabel(strRef=StrRef(f"{_qs(ws.title)}!$M${a}"))
        ls.marker.symbol = "none"
        ls.smooth = False
        ls.graphicalProperties = GraphicalProperties(
            ln=LineProperties(solidFill=COLORS[j % len(COLORS)], w=28575, prstDash="dash")
        )
        chart.series.append(ls)

    # Layout fixo (fração do gráfico) para o título do eixo X nunca cair em cima da legenda
    chart.plot_area.layout = Layout(
        manualLayout=ManualLayout(
            layoutTarget="inner", xMode="edge", yMode="edge", x=0.10, y=0.04, w=0.86, h=0.62
        )
    )
    chart.legend.overlay = False
    chart.legend.layout = Layout(
        manualLayout=ManualLayout(xMode="edge", yMode="edge", x=0.05, y=0.91, w=0.90, h=0.07)
    )
    _axis_title(chart.x_axis, "Time(min)")  # automático: o Excel põe logo abaixo dos números
    _axis_title(chart.y_axis, "Δθ res (mdeg)", pos=(0.01, 0.22))
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.x_axis.scaling.min = 0
    chart.x_axis.majorGridlines = None
    chart.y_axis.majorGridlines = None
    chart.x_axis.tickLblPos = "low"  # rótulos embaixo mesmo com valores negativos
    chart.x_axis.txPr = _txt(1100)
    chart.y_axis.txPr = _txt(1100)
    chart.x_axis.number_format = "0"
    chart.y_axis.number_format = "0"
    # eixo Y automático (o Excel escolhe min/máx conforme os dados)
    ws.add_chart(chart, "F16")
    return last


def _build_compare_sheet(wb, info, levels, compare):
    """Aba 'Comparação': vários canais no mesmo gráfico, com a linha tracejada de cada nível na cor da série
    e o valor escrito em cima dela. Os valores vêm das abas dos canais (mesmas fórmulas)."""
    from openpyxl.chart.label import DataLabel, DataLabelList
    from openpyxl.chart.legend import LegendEntry

    by = {ch.name: (ch, title, last) for ch, title, last in info}
    series = [(by[c], lg) for c, lg in compare if c in by]
    if len(series) < 2:
        return
    ws = wb.create_sheet("Comparação", 0)
    bold, base, inp = Font(name=FONT, bold=True), Font(name=FONT), Font(name=FONT, color="0000FF")
    ws["A1"] = "Comparação de canais"
    ws["A1"].font = Font(name=FONT, bold=True, size=13)
    heads = ["Legenda (pode editar)", "Canal"] + [f"{lv.label} (mdeg)" for lv in levels]
    for i, h in enumerate(heads, 1):
        c = _text(ws.cell(3, i), h)
        c.font = bold
        c.fill = PatternFill("solid", fgColor="DDEBF7")
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    for k, ((ch, title, last), lg) in enumerate(series):
        r = 4 + k
        _text(ws.cell(r, 1), lg).font = inp
        _text(ws.cell(r, 2), ch.name).font = base
        for j in range(len(levels)):
            c = ws.cell(r, 3 + j, f"={_qs(title)}!I{3 + j}")
            c.font, c.number_format = base, "0.000"
    for i, w in zip(range(1, 3 + len(levels)), [30, 14] + [14] * len(levels)):
        ws.column_dimensions[get_column_letter(i)].width = w

    # pontos auxiliares das linhas de nível: (0, meio da janela, fim) por série e nível
    h0 = 6 + len(series)
    ws.cell(h0 - 1, 1, "Auxiliar das linhas de nível").font = bold
    for i, t in enumerate(["x", "y", "rótulo"], 1):
        ws.cell(h0, i, t).font = bold
    chart = ScatterChart()
    chart.style = 2
    chart.scatterStyle = "lineMarker"
    chart.varyColors = False
    chart.height, chart.width = 12, 22
    chart.legend.position = "b"
    chart.legend.txPr = _txt(1100)
    for k, ((ch, title, last), lg) in enumerate(series):
        wsc = wb[title]
        s = Series(
            Reference(wsc, min_col=4, min_row=FIRST_ROW, max_row=last),
            Reference(wsc, min_col=3, min_row=FIRST_ROW, max_row=last),
        )
        s.tx = SeriesLabel(strRef=StrRef(f"{_qs(ws.title)}!$A${4 + k}"))
        s.marker.symbol = "none"
        s.smooth = False
        s.graphicalProperties = GraphicalProperties(
            ln=LineProperties(solidFill=SERIES[k % len(SERIES)], w=34925)
        )
        chart.series.append(s)
    r = h0 + 1
    for k, ((ch, title, last), lg) in enumerate(series):
        col = SERIES[k % len(SERIES)]
        for j, lv in enumerate(levels):
            ws.cell(r, 1, 0)
            ws.cell(r + 1, 1, round((lv.start + lv.end) / 2, 4))
            ws.cell(r + 2, 1, f"=MAX({_qs(title)}!$C${FIRST_ROW}:$C${last})")
            for q in range(3):
                ws.cell(r + q, 2, f"={get_column_letter(3 + j)}{4 + k}").number_format = "0.000"
            ws.cell(r + 1, 3, f'=FIXED({get_column_letter(3 + j)}{4 + k},3,TRUE)&" mdeg"')
            ls = Series(
                Reference(ws, min_col=2, min_row=r, max_row=r + 2),
                Reference(ws, min_col=1, min_row=r, max_row=r + 2),
            )
            ls.tx = SeriesLabel(strRef=StrRef(f"{_qs(ws.title)}!$C${r + 1}"))
            ls.marker.symbol = "none"
            ls.smooth = False
            ls.graphicalProperties = GraphicalProperties(
                ln=LineProperties(solidFill=col, w=22225, prstDash="sysDot")
            )
            ls.dLbls = DataLabelList(
                dLbl=[
                    DataLabel(
                        idx=1,
                        showSerName=True,
                        showVal=False,
                        showCatName=False,
                        showLegendKey=False,
                        showPercent=False,
                        dLblPos="t",
                        txPr=_txt(1000, color=col),
                    )
                ],
                showVal=False,
                showSerName=False,
                showCatName=False,
                showLegendKey=False,
                showPercent=False,
            )
            chart.series.append(ls)
            r += 3
    chart.legend.legendEntry = [
        LegendEntry(idx=i, delete=True) for i in range(len(series), len(chart.series))
    ]
    chart.plot_area.layout = Layout(
        manualLayout=ManualLayout(
            layoutTarget="inner", xMode="edge", yMode="edge", x=0.09, y=0.04, w=0.88, h=0.66
        )
    )
    chart.legend.overlay = False
    _axis_title(chart.x_axis, "Time(min)")
    _axis_title(chart.y_axis, "Δθ res (mdeg)", pos=(0.01, 0.22))
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.x_axis.scaling.min = 0
    chart.x_axis.majorGridlines = None
    chart.y_axis.majorGridlines = None
    chart.x_axis.tickLblPos = "low"
    chart.x_axis.txPr = _txt(1100)
    chart.y_axis.txPr = _txt(1100)
    chart.x_axis.number_format = "0"
    chart.y_axis.number_format = "0"
    ws.add_chart(chart, get_column_letter(4 + len(levels)) + "3")


def build_workbook(channels, levels=None, metric="PeakMinAngle", pair=None, compare=None) -> Workbook:
    levels = levels or []
    if pair is not None and (
        len(pair) != 2 or max(pair) >= len(levels) or min(pair) < 0 or pair[0] == pair[1]
    ):
        pair = None
    wb = Workbook()
    wb.remove(wb.active)
    info = []
    used = {"resumo"}
    for ch in channels:
        ws = wb.create_sheet(_sheet_title(ch.name, used))
        last = _build_channel_sheet(ws, ch, levels, metric, pair)
        info.append((ch, ws.title, last))

    # ---- aba Resumo
    rs = wb.create_sheet("Resumo", 0)
    bold = Font(name=FONT, bold=True)
    base = Font(name=FONT)
    _text(rs["A1"], f"Resumo – {metric}")
    rs["A1"].font = Font(name=FONT, bold=True, size=13)
    heads = ["Canal", "Δ final (mdeg)"] + [f"{lv.label} (mdeg)" for lv in levels]
    if pair:
        heads.append(f"Δ {levels[pair[1]].label} − {levels[pair[0]].label} (mdeg)")
    for i, h in enumerate(heads, 1):
        c = _text(rs.cell(3, i), h)
        c.font = bold
        c.fill = PatternFill("solid", fgColor="DDEBF7")
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    for k, (ch, title, last) in enumerate(info):
        r = 4 + k
        _text(rs.cell(r, 1), ch.name).font = base
        rs.cell(r, 2, f"={_qs(title)}!I11").font = base
        rs.cell(r, 2).number_format = "0.000"
        for j in range(len(levels)):
            c = rs.cell(r, 3 + j, f"={_qs(title)}!I{3 + j}")
            c.font = base
            c.number_format = "0.000"
        if pair:
            c = rs.cell(r, 3 + len(levels), f"={_qs(title)}!I12")
            c.font = base
            c.number_format = "0.000"
    for i in range(1, len(heads) + 1):
        rs.column_dimensions[get_column_letter(i)].width = 18
    rs.cell(
        5 + len(info),
        1,
        "Δ = (y − y inicial) × 1000, acumulado linha a linha. Níveis = média do Δ na janela de tempo definida em cada aba.",
    ).font = Font(name=FONT, italic=True, color="595959")
    if compare and len(compare) >= 2:
        _build_compare_sheet(wb, info, levels, compare)

    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    return wb


def convert(data: bytes, metric="PeakMinAngle", selected=None, levels=None, pair=None, compare=None) -> bytes:
    chans = read_channels(data, metric)
    if compare:
        selected = [c for c, _ in compare]
    if selected:
        chans = [c for c in chans if c.name in selected]
        if not chans:
            raise InputError("Nenhum canal selecionado.")
    wb = build_workbook(chans, levels, metric, pair, compare)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
