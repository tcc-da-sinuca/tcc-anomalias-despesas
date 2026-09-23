FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_APP=wsgi.py

WORKDIR /app

# Dependências primeiro, para aproveitar o cache de camadas do Docker.
# As de desenvolvimento (pytest) entram para permitir "docker compose exec app pytest".
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .

EXPOSE 5000

# O entrypoint aplica as migrations e cria o administrador inicial antes de subir o app.
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
