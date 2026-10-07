# Implantação em VPS (produção)

Guia para colocar o sistema no ar numa VPS Ubuntu/Debian que **já tem Nginx** e um
**domínio** apontando para ela. O sistema roda em Docker; o Nginx da VPS faz o HTTPS e
repassa as requisições para o app, que só escuta na própria máquina.

```
Internet ──HTTPS──► Nginx da VPS (certificado Let's Encrypt via Certbot)
                        │  proxy para 127.0.0.1:8000
                        ▼
              docker compose -f docker-compose.prod.yml
                ├─ app        gunicorn (3 workers), sem modo debug
                ├─ agendador  job de reprocessamento das despesas novas
                └─ db         PostgreSQL 16, sem porta exposta, dados no volume pgdata
```

Requisitos: 2 GB de RAM (os três containers usaram cerca de 720 MB no teste), uns 3 GB de disco
livre, acesso `sudo`. Nos exemplos, troque `anomalias.seudominio.com.br` pelo seu domínio.

Para encurtar os comandos, defina este atalho na sessão do terminal da VPS:

```bash
alias dc="docker compose -f docker-compose.prod.yml"
```

---

## 1. Antes de começar

1. **DNS:** crie um registro `A` (e `AAAA`, se usar IPv6) de `anomalias.seudominio.com.br`
   para o IP da VPS. Confira com `dig +short anomalias.seudominio.com.br`.
2. **Docker:** confira com `docker compose version` (precisa ser v2.24 ou mais nova). Se
   não estiver instalado:
   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER      # saia e entre de novo na sessão SSH depois disso
   sudo systemctl enable --now docker  # sobe o Docker junto com a VPS
   ```
3. **Porta 8000:** o app usa `127.0.0.1:8000`. Confira se está livre com
   `sudo ss -ltnp | grep :8000` (sem saída = livre). Se estiver ocupada, use outra em
   `PORTA_APP` no `.env` e no `proxy_pass` do Nginx.

## 2. Baixar o projeto

```bash
sudo mkdir -p /opt/anomalias && sudo chown $USER: /opt/anomalias
git clone https://github.com/tcc-da-sinuca/tcc-anomalias-despesas.git /opt/anomalias
cd /opt/anomalias
```

## 3. Configurar o `.env`

```bash
cp deploy/env.producao.exemplo .env
chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # rode 3 vezes: chave, senha do banco e senha do admin
nano .env
```

Preencha `SECRET_KEY`, `POSTGRES_PASSWORD`, `ADMIN_EMAIL` e `ADMIN_SENHA`. O app **se
recusa a subir** com os valores de exemplo, com uma `SECRET_KEY` de menos de 32
caracteres ou com uma `ADMIN_SENHA` de menos de 12. Guarde a senha do administrador num
gerenciador de senhas.

## 4. Subir os containers

```bash
dc up -d --build          # a primeira vez leva alguns minutos (instala pandas, scikit-learn...)
dc ps                     # db e app devem ficar "healthy"; o agendador sobe depois do app
dc logs -f app            # Ctrl+C para sair dos logs
curl -s http://127.0.0.1:8000/api/saude   # {"banco": "ok", "status": "ok"}
```

Na primeira subida, o app aplica as migrations, cria o administrador e, com
`SEED_BASE_SINTETICA=1`, carrega a base sintética (5.000 despesas). Logo em seguida, o
**agendador faz a primeira análise sozinho** (aparece como "job agendado" na tela
Análises). Confira:

```bash
dc logs agendador | grep Análise   # "Análise 1: 5000 despesas, 596 alertas novos"
```

## 5. Nginx e HTTPS

```bash
sudo cp deploy/nginx-anomalias.conf /etc/nginx/sites-available/anomalias
sudo sed -i 's/anomalias.seudominio.com.br/SEU-DOMINIO-AQUI/' /etc/nginx/sites-available/anomalias
sudo ln -s /etc/nginx/sites-available/anomalias /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Certificado HTTPS gratuito (Let's Encrypt). Se o certbot não estiver instalado:
#   sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d SEU-DOMINIO-AQUI     # escolha redirecionar HTTP para HTTPS
```

Se a VPS usa `ufw`, libere o Nginx (`sudo ufw allow 'Nginx Full'`). **Não** abra a porta
8000: ela fica presa a `127.0.0.1` e não deve ser acessível de fora.

## 6. Conferir

- `https://SEU-DOMINIO-AQUI/api/saude` responde `{"banco": "ok", "status": "ok"}`.
- `https://SEU-DOMINIO-AQUI` mostra a tela de login; entre com `ADMIN_EMAIL`/`ADMIN_SENHA`.
- O dashboard mostra 5.000 despesas e 596 alertas.

## 7. Acesso para colegas e professores

Crie um usuário `auditor` para cada pessoa em **Configuração → Usuários** (ou
`dc exec app flask criar-usuario --perfil auditor`). Não compartilhe a senha do
administrador. Os dados são sintéticos; nenhuma informação real fica exposta.

Para apresentar com os números do [roteiro de demonstração](ROTEIRO_DEMONSTRACAO.md),
parta de um banco limpo (seção 9, "Recomeçar do zero").

---

## 8. Operação

| Tarefa | Comando (na pasta `/opt/anomalias`) |
|---|---|
| Ver o estado | `dc ps` |
| Ver logs | `dc logs -f app` · `dc logs -f agendador` |
| Atualizar para a versão mais nova do GitHub | `git pull && dc up -d --build` |
| Reiniciar | `dc restart` |
| Parar (mantém os dados) | `dc down` |
| Backup do banco | `dc exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup_$(date +%F).sql` |
| Restaurar um backup (num banco vazio) | `dc exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"' < backup_AAAA-MM-DD.sql` |

Os containers voltam sozinhos quando a VPS reinicia (desde que o serviço do Docker esteja
habilitado, `sudo systemctl enable docker`). Os logs de cada container ficam limitados a
30 MB.

## 9. Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `502 Bad Gateway` no navegador | O app ainda está subindo ou caiu | `dc ps` e `dc logs app`; espere ficar `healthy` |
| `SECRET_KEY de exemplo ou curta demais` nos logs | `.env` sem preencher | Gere a chave (seção 3) e rode `dc up -d` |
| `ADMIN_SENHA precisa ser trocada` nos logs | Senha de exemplo ou curta | Troque no `.env` e rode `dc up -d` |
| O login volta sempre para a tela de login | Acesso por `http://`: em produção o cookie de sessão só trafega por HTTPS | Configure o HTTPS (seção 5) e acesse por `https://` |
| `413 Request Entity Too Large` ao importar | Limite de upload do Nginx | Confira `client_max_body_size 16m;` no site |
| Recomeçar do zero (banco limpo) | — | `dc down -v && dc up -d`; depois a primeira análise (seção 4). **Apaga todos os dados** |
