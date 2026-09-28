# Use an official lightweight Python image (aligned with pyproject requires-python>=3.12).
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=core.settings_saas

# System libs for weasyprint/pillow (see INSTALL.md) + postgres client for debugging
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 libcairo2 \
    libgdk-pixbuf-2.0-0 libharfbuzz-subset0 libharfbuzz0b libopenjp2-7 libjpeg-turbo8 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN addgroup --system app && adduser --system --group app

# Set work directory
WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "import django; print(django.get_version())"

# Copy project (respects .dockerignore: excludes .git, .env, sqlite, media/cache, docs/plans)
COPY . /app/

# Collect static at build time so runtime does not serve stale assets
RUN python manage.py collectstatic --noinput --settings=core.settings_test || echo "collectstatic skipped"

# Drop build-time bloat that must never ship
RUN rm -f /app/test_db.sqlite3 /app/*.csv \
    && rm -rf /app/htmlcov /app/.coverage /app/test-emails \
    && chown -R app:app /app

# Change to the app user
USER app

# Health check for orchestrators (gunicorn on :8000)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/')" || exit 1

# Expose the port
EXPOSE 8000

# Run gunicorn (settings module provided by env; default to SaaS overlay in prod)
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]
