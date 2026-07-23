FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ASL_DATA_DIR=/data

WORKDIR /app

RUN groupadd --system asl \
    && useradd --system --gid asl --home-dir /app --shell /usr/sbin/nologin asl

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hub/ ./hub/

RUN mkdir -p /data \
    && chown -R asl:asl /app /data

USER asl

EXPOSE 8080

CMD ["uvicorn", "hub.main:app", "--host", "0.0.0.0", "--port", "8080"]
