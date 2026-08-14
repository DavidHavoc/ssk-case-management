FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system ssk && useradd --system --gid ssk --home /app ssk

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY config ./config
COPY templates ./templates
COPY static ./static
COPY locale ./locale
COPY manage.py ./manage.py

RUN python -m pip install . && \
    mkdir -p /app/media/private /app/staticfiles && \
    DJANGO_DEBUG=0 \
    DJANGO_SECRET_KEY=build-only-static-secret-key-with-at-least-fifty-characters-12345 \
    DJANGO_ALLOWED_HOSTS=build.invalid \
    DATABASE_URL=postgresql://build:build@build.invalid:5432/build \
    DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend \
    DJANGO_DEFAULT_FROM_EMAIL=build@build.invalid \
    EMAIL_HOST=build.invalid \
    EMAIL_USE_TLS=1 \
    python manage.py collectstatic --noinput && \
    chown -R ssk:ssk /app/media/private /app/staticfiles

USER ssk
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--config", "config/gunicorn.conf.py"]
