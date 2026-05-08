FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY common ./common
COPY sources ./sources
COPY main.py ./
RUN pip install --upgrade pip && pip install .

# Override at runtime: `python main.py cra` or set SOURCE env var.
CMD ["python", "main.py"]
