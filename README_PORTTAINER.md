# 🚀 Deploy no Portainer - Sistema de Protocolo CGM

Guia rápido para fazer deploy do Sistema de Protocolo no Portainer com banco de dados PostgreSQL local.

## ⚡ Início Rápido

### 1. Configurar Variáveis de Ambiente

No Portainer, crie um arquivo `.env` na pasta do projeto ou use a interface de **Environment Variables**:

```env
DJANGO_SECRET_KEY=sua-chave-secreta-aqui
DJANGO_DEBUG=False
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@saquarema.rj.gov.br
DJANGO_SUPERUSER_PASSWORD=sua-senha-segura
POSTGRES_DB=protocolo_db
POSTGRES_USER=protocolo_user
POSTGRES_PASSWORD=sua-senha-banco-segura
POSTGRES_HOST=db
```

### 2. Deploy no Portainer

#### Método 1: Via Web Editor (Mais Fácil)

1. Acesse Portainer
2. Vá em **Stacks** → **Add Stack**
3. Escolha **Web editor**
4. Cole o conteúdo de `portainer-stack.yml`
5. Configure as variáveis de ambiente na seção **Environment Variables**
6. Clique em **Deploy the stack**

#### Método 2: Via Docker Compose

```bash
# No servidor
cd /caminho/do/projeto
docker-compose up -d --build
```

### 3. Acessar a Aplicação

- **URL**: `http://seu-servidor:8800`
- **Admin**: `http://seu-servidor:8800/admin`
- **Login**: admin / (senha configurada)

## 📦 Migração de Dados do Supabase

### Opção 1: SQL Dump

```bash
# Exportar do Supabase (no painel web ou terminal)
pg_dump -h db.supabase.co -U postgres -d postgres > backup.sql

# Importar no banco local
docker exec -i protocolo_db psql -U protocolo_user -d protocolo_db < backup.sql
```

### Opção 2: Usando Script

```bash
# Dar permissão de execução
chmod +x migracao_rapida.sh

# Executar
./migracao_rapida.sh
```

### Opção 3: Backup do Supabase

1. Acesse o painel do Supabase
2. Vá em **Database** → **Backups**
3. Faça download do backup SQL
4. Importe:

```bash
docker cp backup.sql protocolo_db:/tmp/backup.sql
docker exec protocolo_db psql -U protocolo_user -d protocolo_db -f /tmp/backup.sql
```

## 🔧 Comandos Úteis

### Ver Logs
```bash
# Logs em tempo real
docker logs -f protocolo_web

# Logs do banco
docker logs -f protocolo_db
```

### Acessar Shell Django
```bash
docker exec -it protocolo_web python manage.py shell
```

### Criar Superusuário
```bash
docker exec -it protocolo_web python manage.py createsuperuser
```

### Backup Manual
```bash
docker exec protocolo_db pg_dump -U protocolo_user protocolo_db > backup_$(date +%Y%m%d).sql
```

### Restaurar Backup
```bash
docker exec -i protocolo_db psql -U protocolo_user -d protocolo_db < backup.sql
```

## 📊 Monitoramento

### Ver Status
```bash
docker ps
```

### Ver Recursos
```bash
docker stats
```

### Acessar PostgreSQL
```bash
docker exec -it protocolo_db psql -U protocolo_user -d protocolo_db
```

## 🔄 Atualizar Aplicação

```bash
# Parar containers
docker-compose down

# Atualizar código (git pull ou upload de arquivos)
git pull

# Reconstruir e iniciar
docker-compose up -d --build

# Reexecutar migrações
docker exec -it protocolo_web python manage.py migrate
```

## 🆘 Solução de Problemas

### Container não inicia
```bash
docker logs protocolo_web
```

### Erro de conexão com banco
```bash
docker exec protocolo_db pg_isready -U protocolo_user
```

### Resetar completo
⚠️ **CUIDADO**: Apaga todos os dados!
```bash
docker-compose down -v
docker volume rm protocolo_cgm-main_postgres_data
docker-compose up -d --build
```

## 📁 Estrutura

```
.
├── docker-compose.yml      # Para docker-compose CLI
├── portainer-stack.yml     # Para Portainer Web Editor
├── Dockerfile
├── env.example
├── .env                    # Criar este arquivo
├── setup_portainer.sh      # Script de setup
└── migracao_rapida.sh      # Script de migração
```

## 🔒 Segurança

- ✅ Use senhas fortes
- ✅ Configure firewall (portas 8800, 5432)
- ✅ Use HTTPS em produção
- ✅ Mantenha backups regulares
- ❌ NUNCA faça commit do `.env`

## 📞 Ajuda

Para mais detalhes, leia: **DEPLOY_PORTTAINER.md**

---

**Desenvolvido para**: Controladoria Geral do Município de Saquarema/RJ
