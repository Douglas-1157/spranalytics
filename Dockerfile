FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 MPLBACKEND=Agg SPR_BEHIND_PROXY=1
WORKDIR /app
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt
COPY . .

RUN useradd --system --uid 10001 --no-create-home app && chown -R app /app
USER app

CMD exec gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-8080}
