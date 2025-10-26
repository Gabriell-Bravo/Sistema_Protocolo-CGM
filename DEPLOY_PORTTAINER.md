# Deploy no Portainer - Sistema de Protocolo CGM

Este guia explica como fazer o deploy do Sistema de Protocolo no Portainer com banco de dados PostgreSQL local.

## 📋 Pré-requisitos

- Portainer instalado e configurado
- Acesso ao servidor onde o Portainer está rodando
- Git configurado (opcional, para clonar o repositório)

## 🚀 Passos para Deploy

### 1. Preparar o Ambiente

#### Opção A: Via Git (Recomendado)
```bash
# Se o repositório estiver em Git
git clone <seu-repositorio>
cd Sistema_Protocolo-CGM
```

#### Opção B: Enviar arquivos diretamente
Faça upload dos arquivos do projeto para o servidor via SFTP ou outra ferramenta.

### 2. Configurar Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto baseado no `env.example`:

```bash
cp env.example .env
```

Edite o arquivo `.env` com suas configurações:

```env
# Django Settings
DJANGO_SECRET_KEY=sua-chave-secreta-muito-segura-aqui
DJANGO_DEBUG=False

# Superuser Configuration
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@saquarema.rj.gov.br
DJANGO_SUPERUSER_PASSWORD=sua-senha-segura-aqui

# PostgreSQL Database Configuration
POSTGRES_DB=protocolo_db
POSTGRES_USER=protocolo_user
POSTGRES_PASSWORD=sua-senha-banco-segura-aqui
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Timezone
TZ=America/Sao_Paulo
```

⚠️ **IMPORTANTE**: Altere todas as senhas para valores seguros!

### 3. Deploy no Portainer

#### 3.1. Via Stacks (Recomendado)

1. Acesse o Portainer
2. Vá em **Stacks** > **Add Stack**
3. Escolha **Web editor**
4. Cole o conteúdo do arquivo `docker-compose.yml`
5. Clique em **Deploy the stack**

#### 3.2. Via Docker Compose (Terminal)

Se você tem acesso SSH ao servidor:

```bash
# Navegue até a pasta do projeto
cd /caminho/para/o/projeto

# Faça build e inicie os containers
docker-compose up -d --build

# Verifique os logs
docker-compose logs -f
```

### 4. Verificar Deploy

Acesse a aplicação em:
- **URL**: `http://seu-servidor:8800`
- **Admin**: `http://seu-servidor:8800/admin`

As credenciais padrão são:
- Usuário: `admin`
- Senha: (configurada no `.env` como `DJANGO_SUPERUSER_PASSWORD`)

## 📦 Migração de Dados do Supabase

### Opção 1: Backup SQL via Supabase

1. Acesse o painel do Supabase
2. Vá em **Settings** > **Database**
3. Faça download do backup ou use o **SQL Editor** para exportar

4. Importe no PostgreSQL local:

```bash
# Copie o arquivo SQL para o container
docker cp backup.sql protocolo_db:/tmp/backup.sql

# Importe os dados
docker exec -i protocolo_db psql -U protocolo_user -d protocolo_db < /tmp/backup.sql
```

### Opção 2: Export/Import via Python

1. Exporte dados do Supabase:

```python
# No ambiente com Supabase configurado
python manage.py dumpdata > supabase_backup.json
```

2. Importe no banco local:

```bash
# Copie o arquivo para o container
docker cp supabase_backup.json protocolo_web:/app/supabase_backup.json

# Importe os dados
docker exec -it protocolo_web python manage.py loaddata supabase_backup.json
```

### Opção 3: Migração Direta via psql

Se você tem acesso direto ao Supabase:

```bash
# Exportar do Supabase
pg_dump -h db.supabase.co -U postgres -d postgres > backup.sql

# Importar no PostgreSQL local
docker exec -i protocolo_db psql -U protocolo_user -d protocolo_db < backup.sql
```

## 🔧 Comandos Úteis

### Ver logs dos containers
```bash
docker-compose logs -f web    # Logs da aplicação
docker-compose logs -f db     # Logs do banco
```

### Acessar Django shell
```bash
docker exec -it protocolo_web python manage.py shell
```

### Criar superusuário manualmente
```bash
docker exec -it protocolo_web python manage.py createsuperuser
```

### Fazer backup do banco
```bash
docker exec protocolo_db pg_dump -U protocolo_user protocolo_db > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restaurar backup
```bash
docker exec -i protocolo_db psql -U protocolo_user -d protocolo_db < backup.sql
```

### Reexecutar migrações
```bash
docker exec -it protocolo_web python manage.py makemigrations
docker exec -it protocolo_web python manage.py migrate
```

## 📊 Monitoramento

### Ver status dos containers
```bash
docker-compose ps
```

### Ver uso de recursos
```bash
docker stats
```

### Acessar PostgreSQL
```bash
docker exec -it protocolo_db psql -U protocolo_user -d protocolo_db
```

## 🔄 Atualização da Aplicação

Quando houver atualizações:

```bash
# Parar os containers
docker-compose down

# Atualizar o código
git pull  # ou faça upload dos novos arquivos

# Reconstruir e iniciar
docker-compose up -d --build

# Reexecutar migrações se necessário
docker exec -it protocolo_web python manage.py migrate
```

## 🆘 Troubleshooting

### Container não inicia
```bash
# Ver logs
docker-compose logs web

# Verificar configurações
cat .env
```

### Erro de conexão com banco
```bash
# Verificar se o banco está respondendo
docker exec protocolo_db pg_isready -U protocolo_user

# Ver configurações do banco
docker exec protocolo_db psql -U protocolo_user -c '\l'
```

### Erro de permissões
```bash
# Ajustar permissões
sudo chown -R $USER:$USER .
sudo chmod -R 755 .
```

### Resetar banco de dados
⚠️ **CUIDADO**: Isso apaga todos os dados!

```bash
docker-compose down -v
docker volume rm protocolo_cgm-main_postgres_data
docker-compose up -d
```

## 📝 Estrutura de Arquivos

```
.
├── docker-compose.yml      # Configuração do Portainer/Docker
├── Dockerfile              # Build da aplicação
├── env.example             # Template de variáveis
├── .env                    # Suas configurações (NÃO COMMITAR)
├── requirements.txt        # Dependências Python
├── protocolo_project/      # Configurações Django
├── processos_app/          # Aplicação principal
├── templates/              # Templates HTML
└── staticfiles_build/      # Arquivos estáticos
```

## 🔒 Segurança

1. **Nunca** faça commit do arquivo `.env`
2. Use senhas fortes em produção
3. Configure firewall adequadamente
4. Considere usar HTTPS com nginx ou Traefik
5. Mantenha backups regulares do banco de dados

## 📞 Suporte

Para problemas ou dúvidas:
- Verifique os logs: `docker-compose logs`
- Consulte a documentação do Django
- Entre em contato com a equipe de TI

---

**Desenvolvido para**: Controladoria Geral do Município de Saquarema/RJ
