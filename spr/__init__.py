"""SprAnalytics: do CSV do Sensorgrama ao Excel e ao gráfico."""

from .charts import convert_charts, convert_compare_chart, render_chart
from .config import MAX_CHANNELS, MAX_COLS, MAX_ROWS
from .excel import build_workbook, convert
from .levels import deltas, detect_levels, detect_levels_multi, level_value
from .models import Channel, InputError, Level
from .parsing import clean_text, list_metrics, read_channels, safe_name

__all__ = [
    "Channel",
    "InputError",
    "Level",
    "MAX_CHANNELS",
    "MAX_COLS",
    "MAX_ROWS",
    "build_workbook",
    "clean_text",
    "convert",
    "convert_charts",
    "convert_compare_chart",
    "deltas",
    "detect_levels",
    "detect_levels_multi",
    "level_value",
    "list_metrics",
    "read_channels",
    "render_chart",
    "safe_name",
]
