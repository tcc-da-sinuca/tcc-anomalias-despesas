#!/bin/sh
# Prepara o banco e inicia o comando recebido (por padrão, o servidor Flask).
set -e

echo ">> Aplicando migrations..."
flask db upgrade

echo ">> Garantindo administrador inicial e parâmetros padrão..."
flask seed-admin

if [ "${SEED_BASE_SINTETICA:-0}" = "1" ]; then
    echo ">> Carregando a base sintética (não faz nada se já estiver carregada)..."
    flask seed-base
fi

exec "$@"
