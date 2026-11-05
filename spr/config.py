"""Constantes compartilhadas: limites de segurança, fonte e paletas de cores."""

# ---- limites (o arquivo real tem ~600 linhas e 176 colunas; sobra folga)
MAX_ROWS = 20_000
MAX_COLS = 400
MAX_CHANNELS = 24

# ---- planilha
FONT = "Arial"
FIRST_ROW = 3  # primeira linha de dados (como no teste_l1 do professor)

# ---- cores (hex sem '#')
COLORS = ["ED7D31", "1E6B1E", "7030A0", "C00000"]  # linhas de nível
SERIES = ["1A5F82", "ED7D31", "1E6B1E", "7030A0"]  # uma cor por canal comparado
