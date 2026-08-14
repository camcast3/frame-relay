FROM python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ASL_DATA_DIR=/data

WORKDIR /app

RUN groupadd --system asl \
    && useradd --system --gid asl --home-dir /app --shell /usr/sbin/nologin asl

COPY requirements.txt .
# The final container never installs packages at runtime. Remove installers/build helpers and
# Debian's unused Perl runtime after the hash-verified install to eliminate their CVE surface.
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
    && pip uninstall --yes setuptools wheel jaraco.context \
    && pip uninstall --yes pip \
    && dpkg --purge --force-remove-essential perl-base

COPY hub/ ./hub/

RUN mkdir -p /data \
    && chown -R asl:asl /app /data

USER asl

EXPOSE 8080

CMD ["uvicorn", "hub.main:app", "--host", "0.0.0.0", "--port", "8080"]
