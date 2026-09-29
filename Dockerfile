FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --system --uid 1000 adapter

COPY . .

# Writable data directories, declared as volumes; created here so that new volumes inherit the ownership
RUN mkdir -p log jobs uploads && chown adapter:adapter log jobs uploads
VOLUME ["/app/log", "/app/jobs", "/app/uploads"]

USER adapter
EXPOSE 5000

HEALTHCHECK --interval=60s --timeout=15s --start-period=15s --retries=3 \
    CMD ["python", "healthcheck.py"]

# One worker with several threads: async jobs run in-process and must stay in the same process
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "300", "--bind", "0.0.0.0:5000", "app:app"]
