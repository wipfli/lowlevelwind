FROM python:3.11-slim

ENV POETRY_VERSION=1.8.2 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    DEBIAN_FRONTEND=noninteractive \
    PIPX_BIN_DIR=/usr/local/bin \
    PIPX_HOME=/opt/pipx

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libffi-dev libssl-dev \
    python3-pip python3-venv pipx \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 - --version $POETRY_VERSION \
    && ln -s ~/.local/bin/poetry /usr/local/bin/poetry

WORKDIR /app

COPY poetry.lock poetry.lock
COPY pyproject.toml pyproject.toml

RUN poetry install

RUN pip3 install zarr s3fs

