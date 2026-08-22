FROM python:3.11-slim-bookworm

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    ffmpeg \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev \
    libasound2-dev \
    espeak-ng \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"
RUN poetry config virtualenvs.create false

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock /app/

# Install python dependencies
RUN poetry install --no-root --no-interaction --no-ansi

# Copy project files
COPY . /app/

# Default entrypoint to run in text mode
ENTRYPOINT ["poetry", "run", "python", "main.py"]
CMD ["--mode", "text"]
