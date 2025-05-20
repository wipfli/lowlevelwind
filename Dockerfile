# Use official Python 3.11 slim base image
FROM python:3.11-slim

# Set environment variables
ENV POETRY_VERSION=1.8.2 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    DEBIAN_FRONTEND=noninteractive \
    PIPX_BIN_DIR=/usr/local/bin \
    PIPX_HOME=/opt/pipx

# Install system dependencies + pipx
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git libffi-dev libssl-dev \
    python3-pip python3-venv pipx \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - --version $POETRY_VERSION \
    && ln -s ~/.local/bin/poetry /usr/local/bin/poetry

# Install JupyterLab via pipx
RUN pipx install jupyterlab

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies with Poetry
RUN poetry install

# Install Jupyter kernel into global user environment
RUN poetry run python -m ipykernel install --user --name=notebooks-nwp-env --display-name "Python (notebooks-nwp-env)"

# Expose JupyterLab port
EXPOSE 8888

# Default command to launch JupyterLab
CMD bash -c "poetry run jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root"
