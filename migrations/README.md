# Migrations

Gerenciadas pelo Flask-Migrate (Alembic).

```bash
flask db upgrade                       # aplica todas as migrations
flask db migrate -m "Descreve a mudança"   # gera uma nova migration a partir dos modelos
flask db downgrade                     # desfaz a última migration
```

Revise sempre a migration gerada antes de fazer commit. Lembre-se de que
mudanças em entidades afetam o diagrama de classes: registre-as em
`docs/MUDANCAS_PARA_DOCUMENTACAO.md`.

O teste `tests/test_models/test_postgres.py::test_migrations_refletem_modelos`
falha se os modelos e as migrations ficarem dessincronizados.
