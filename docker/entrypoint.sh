#!/bin/sh
# Prepara o banco e inicia o comando recebido (por padrão, o servidor Flask).
set -e

echo ">> Aplicando migrations..."
flask db upgrade

echo ">> Garantindo administrador inicial e parâmetros padrão..."
flask seed-admin

exec "$@"
