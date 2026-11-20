FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    GEM_HOST=0.0.0.0 \
    GEM_PORT=8000 \
    GEM_DB_PATH=/data/tasks.db

WORKDIR /app
COPY pyproject.toml README.md ./
COPY gem_ergency_room ./gem_ergency_room
RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 gem \
    && mkdir /data && chown gem /data

USER gem
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:'+os.environ.get('GEM_PORT','8000')+'/healthz', timeout=2)"

CMD ["gem-ergency-room"]
