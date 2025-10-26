# 🪟 Deploy no Portainer via Windows - Método Mais Fácil

Como você está no Windows, a forma mais fácil é fazer o deploy direto da sua máquina local para o servidor Portainer.

## ✅ Opção Mais Simples: Deploy Direto da Máquina Local

### Pré-requisitos

1. **Docker Desktop** instalado no Windows
2. Ou acesso ao servidor via SSH
3. Arquivo `.env` já criado (você já tem!)

### Passo 1: Preparar o Projeto

Você já está na pasta correta:
```
c:\Users\gabriel bravo\Desktop\GABRIEL\estagio\Sistema_Protocolo-CGM-main
```

### Passo 2: Deploy via Terminal

Abra o PowerShell nesta pasta e execute:

```powershell
# Verificar se está na pasta correta
pwd

# Fazer deploy (irá buildar e subir os containers)
docker-compose up -d --build

# Aguardar alguns minutos e verificar logs
docker-compose logs -f
```

### Passo 3: Se os containers subirem com sucesso

Os containers estarão rodando na sua máquina local. Para acessar:
- URL: `http://localhost:8800`
- Admin: `http://localhost:8800/admin`

### Passo 4: Transferir para o Servidor Portainer

Agora que funciona localmente, você precisa transferir para o servidor.

**Opção A - Via PowerShell (sem Git):**

```powershell
# Compactar tudo
Compress-Archive -Path .\* -DestinationPath sistema-protocolo.zip -Force

# Você precisará fazer upload manual deste zip para o servidor
# Via WinSCP, FileZilla, ou SFTP
```

**Opção B - Via Git (Recomendado):**

```powershell
# Se o projeto já estiver no Git
git status
git add .
git commit -m "Configuração para Portainer"
git push

# Depois, no Portainer:
# Stacks → Add Stack → Repository
# URL: https://github.com/seu-usuario/repositorio.git
```

---

## 🚀 Método Recomendado: Git

### 1. Criar repositório no GitHub

1. Vá para https://github.com
2. Clique em **"New repository"**
3. Nome: `sistema-protocolo-cgm`
4. **NÃO** inicialize com README (já tem arquivos)
5. Clique em **"Create repository"**

### 2. Fazer upload do código

No PowerShell:

```powershell
# Verificar se está na pasta do projeto
cd "c:\Users\gabriel bravo\Desktop\GABRIEL\estagio\Sistema_Protocolo-CGM-main"

# Inicializar Git (se ainda não tiver)
git init

# Adicionar arquivo .gitignore para não commitar .env
# (já existe .gitignore no projeto)
# Verificar que o .env NÃO está sendo versionado
git status

# Adicionar todos os arquivos
git add .

# Commit
git commit -m "Sistema de Protocolo CGM - Deploy Portainer"

# Conectar com GitHub
git remote add origin https://github.com/SEU-USUARIO/sistema-protocolo-cgm.git

# Push
git push -u origin main
```

### 3. No Portainer

1. **Stacks** → **Add Stack**
2. **Nome**: `sistema_protocolo`
3. **Build method**: **Repository**
4. **Repository URL**: `https://github.com/SEU-USUARIO/sistema-protocolo-cgm.git`
5. **Repository reference**: `main`
6. **Compose path**: `docker-compose.yml`

### 4. Adicionar Variáveis de Ambiente

Na seção "Environment variables", cole:

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

### 5. Deploy

Clique em **"Deploy the stack"**

---

## 🎯 Qual Método Usar?

**Recomendo o método Git** porque é o mais profissional e fácil de manter.

Se você não tem conta no GitHub, crie uma (é grátis): https://github.com/join

---

## 🔍 Verificar Depois do Deploy

No Portainer:
- Stacks → `sistema_protocolo`
- Ver se os containers estão rodando
- Ver logs: clique em cada container → Logs

Acessar:
- `http://172.16.32.198:8800`
- `http://172.16.32.198:8800/admin`

Login: admin / burgess-scrapes-traitors-sulus

