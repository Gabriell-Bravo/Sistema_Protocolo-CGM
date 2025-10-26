# 🎯 Instruções Visuais para Deploy no Portainer

## ❌ O Problema
O erro que você está vendo é:
```
env file /data/compose/14/.env not found
```

Isso acontece porque o `docker-compose.yml` referencia um arquivo `.env` que não existe no servidor do Portainer.

## ✅ A Solução

Você precisa adicionar as variáveis de ambiente **diretamente no Portainer**.

---

## 📝 Passo a Passo Detalhado

### 1️⃣ No Portainer, vá para a seção "Environment variables"

Na página "Create stack", logo abaixo do editor de código, você verá uma seção chamada **"Environment variables"**.

### 2️⃣ Copie e cole TODAS estas variáveis

Abra o arquivo `VARIAVEIS_PORTAINER.txt` que foi criado no projeto, ou copie deste texto:

```
DJANGO_SECRET_KEY=!m-f!1@4y^^m8$2v588t&a6!+t(1!81%!j5+&ee4e(w5mtt)1e
DJANGO_DEBUG=True
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=gabrielbravo4321@gmail.com
DJANGO_SUPERUSER_PASSWORD=burgess-scrapes-traitors-sulus
POSTGRES_DB=protocolo_db
POSTGRES_USER=Controladoria
POSTGRES_PASSWORD=Cgmroot
POSTGRES_HOST=db
TZ=America/Sao_Paulo
WEB_PORT=8800
POSTGRES_PORT=5432
```

### 3️⃣ Adicionar no Portainer

No campo "Environment variables" do Portainer, cole as variáveis de duas formas:

**Opção A: Copiar tudo de uma vez (mais fácil)**
- Cole todo o bloco acima no campo de texto
- O Portainer vai separar automaticamente cada linha como uma variável

**Opção B: Adicionar uma por uma**
- Clique em "Add" para cada variável
- Preencha o nome e valor

### 4️⃣ Copiar o código do docker-compose

No editor "Web editor", cole o conteúdo do arquivo **`portainer-stack.yml`**:

```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    container_name: protocolo_db
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data/
    environment:
      POSTGRES_DB: '${POSTGRES_DB}'
      POSTGRES_USER: '${POSTGRES_USER}'
      POSTGRES_PASSWORD: '${POSTGRES_PASSWORD}'
      TZ: America/Sao_Paulo
      PGTZ: GMT-3
    ports:
      - '5432:5432'
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}']
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - protocolo_network

  web:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: protocolo_web
    restart: unless-stopped
    command: >
      bash -c "
        echo 'Aguardando banco de dados...';
        sleep 5;
        python manage.py makemigrations;
        python manage.py migrate;
        python manage.py createsuperuser --noinput || true;
        python manage.py collectstatic --noinput;
        echo 'Iniciando aplicação...';
        gunicorn --bind 0.0.0.0:8800 --workers 3 --timeout 120 protocolo_project.wsgi:application
      "
    volumes:
      - ./staticfiles_build:/app/staticfiles_build
      - ./mediafiles:/app/mediafiles
    ports:
      - '8800:8800'
    environment:
      DJANGO_SECRET_KEY: '${DJANGO_SECRET_KEY}'
      DJANGO_DEBUG: '${DJANGO_DEBUG}'
      DJANGO_SUPERUSER_USERNAME: '${DJANGO_SUPERUSER_USERNAME}'
      DJANGO_SUPERUSER_EMAIL: '${DJANGO_SUPERUSER_EMAIL}'
      DJANGO_SUPERUSER_PASSWORD: '${DJANGO_SUPERUSER_PASSWORD}'
      TZ: America/Sao_Paulo
      POSTGRES_DB: '${POSTGRES_DB}'
      POSTGRES_USER: '${POSTGRES_USER}'
      POSTGRES_PASSWORD: '${POSTGRES_PASSWORD}'
      POSTGRES_HOST: '${POSTGRES_HOST}'
      POSTGRES_PORT: 5432
    depends_on:
      db:
        condition: service_healthy
    networks:
      - protocolo_network

volumes:
  postgres_data:
    driver: local

networks:
  protocolo_network:
    driver: bridge
```

### 5️⃣ Deploy

1. Nome da Stack: `sistema_protocolo`
2. Clique em **"Deploy the stack"**
3. Aguarde o build (pode levar alguns minutos)

---

## 🎨 Como Adicionar Variáveis (Interface Visual)

Na seção "Environment variables", você verá algo assim:

```
┌─────────────────────────────────────────┐
│ Environment variables                   │
├─────────────────────────────────────────┤
│                                         │
│  ┌────────────────────────────────┐    │
│  │ DJANGO_SECRET_KEY=...          │    │
│  │ DJANGO_DEBUG=True              │    │
│  │ DJANGO_SUPERUSER_USERNAME=...  │    │
│  │ ...                             │    │
│  └────────────────────────────────┘    │
│                                         │
│ [Add] [Remove]                         │
└─────────────────────────────────────────┘
```

**Cole todo o texto do `VARIAVEIS_PORTAINER.txt` nessa área!**

---

## 🔍 Verificação

Após o deploy, verifique:

1. **Ir para Stacks** → `sistema_protocolo`
2. Verificar que os containers estão rodando:
   - `protocolo_db` (postgres)
   - `protocolo_web` (Django)

3. **Acessar a aplicação**:
   - URL: `http://172.16.32.198:8800`
   - Admin: `http://172.16.32.198:8800/admin`

4. **Login**:
   - Usuário: `admin`
   - Senha: `burgess-scrapes-traitors-sulus`

---

## 🆘 Se ainda der erro

1. Verifique se copiou TODAS as 12 variáveis
2. Verifique se não há espaços extras nas variáveis
3. Certifique-se de usar o conteúdo de `portainer-stack.yml` no editor
4. Ver os logs: Vá em Stacks → `sistema_protocolo` → Logs

---

**Dica**: Depois de adicionar as variáveis, o Portainer criará automaticamente o arquivo `.env` na stack. Não precisa fazer upload manual do arquivo!

