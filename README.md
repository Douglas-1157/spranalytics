# SprAnalytics

Site que transforma o arquivo CSV do **Sensorgrama** (equipamento de SPR, ressonância de plasmon de superfície) em:

- **Excel** com as contas feitas por fórmulas (tempo, Δθ em mdeg), tabela de níveis e gráfico pronto;
- **só o gráfico** em PNG, JPG ou PDF;
- **comparação de canais** no mesmo gráfico (ex.: L1 × L3), com a média de cada nível escrita em cima da linha pontilhada.

Projeto feito para ajudar um laboratório de pesquisa que estuda peçonhas, onde essas contas eram feitas à mão em planilhas.

## Recursos
- Detecção automática dos níveis (patamares estáveis após cada queda) e Δ entre níveis
- Níveis editáveis, prévia do gráfico em tempo real
- Interface simples, responsiva, em português
- Segurança com base no OWASP Top 10

## Tecnologias
Python, Flask, openpyxl, matplotlib, JavaScript puro (sem bibliotecas externas), gunicorn.

## Estrutura do código
```
app.py            servidor Flask: rotas, limites de uso, senha e cabeçalhos de segurança
spr/
  config.py       limites, fonte e cores
  models.py       Channel, Level e o erro InputError
  parsing.py      leitura do CSV e limpeza de textos
  levels.py       delta e detecção automática dos níveis
  excel.py        planilha com fórmulas e gráficos
  charts.py       gráficos em PNG, JPG e PDF (inclui a comparação)
static/           tela do site (HTML, CSS, JavaScript)
```

## Como rodar no seu computador
```
pip install -r requirements.txt
python app.py
```
Depois abra http://127.0.0.1:5000. No Windows, basta dar dois cliques em `iniciar.bat`.

