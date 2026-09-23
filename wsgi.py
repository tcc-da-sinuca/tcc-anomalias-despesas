"""Ponto de entrada da aplicação (flask run / gunicorn wsgi:app)."""

from app import create_app

app = create_app()
