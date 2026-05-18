FROM python:3.11-slim

# System deps required by pygame in headless mode (SDL libs are still needed).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libsdl2-2.0-0 \
        libsdl2-image-2.0-0 \
        libsdl2-mixer-2.0-0 \
        libsdl2-ttf-2.0-0 \
        libfreetype6 \
        libportmidi0 \
        fontconfig \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Force pygame to use the dummy video driver — no display required.
ENV SDL_VIDEODRIVER=dummy \
    SDL_AUDIODRIVER=dummy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app
COPY tests /app/tests
COPY README.md /app/README.md

# Run as a non-root user.
RUN useradd --create-home --uid 1000 sim \
    && chown -R sim:sim /app
USER sim

ENTRYPOINT ["python", "-m", "app.main"]
CMD ["--scenario", "symmetric", "--mode", "baseline", "--duration", "600", "--headless"]
