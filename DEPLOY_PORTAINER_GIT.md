# 🚀 Deploy via Portainer com Git (Método Recomendado)

## 📋 Pré-requisitos

1. Seu código precisa estar em um repositório Git (GitHub, GitLab, etc.)
2. Acesso ao repositório (URL pública ou token de acesso)

## 🔧 Passo a Passo

### Opção 1: Deploy Via Git Repository (Melhor Opção)

#### 1. Colocar código no GitHub/GitLab

Primeiro, faça commit e push do seu código:

```powershell
# No PowerShell, na pasta do projeto
cd "c:\Users\gabriel bravo\Desktop\GABRIEL\estagio\Sistema_Protocolo-CGM-main"

# Verificar status do Git
git status

# Adicionar todos os arquivos
git add .

# Commit
git commit -m "Deploy para Portainer"

# Se já tiver remote configurado
git push

# OU criar novo repositório no GitHub e adicionar:
# git remote add origin https://github.com/seu-usuario/sistema-protocolo.git
# git push -u origin main
```

#### 2. No Portainer, use "Repository" method

1. **Acesse Portainer** → Stacks → Add Stack
2. **Nome**: `sistema_protocolo`
3. **Build method**: Escolha **"Repository"**
4. **Preencha**:
   - **Repository URL**: `https://github.com/seu-usuario/sistema-protocolo.git`
   - **Repository reference**: `main` ou `master`
   - **Compose file path**: `docker-compose.yml` ou deixe vazio

#### 3. Configurar variáveis de ambiente

Na seção "Environment variables", adicione:

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

#### 4. Deploy

Clique em **"Deploy the stack"**

---

### Opção 2: Deploy via SSH/Terminal Direto

Se você tem acesso SSH ao servidor:

```bash
# Conectar ao servidor via SSH
ssh usuario@172.16.32.198

# Clonar ou fazer upload do código
cd /var/docker-data
git clone https://github.com/seu-usuario/sistema-protocolo.git
cd sistema-protocolo

# Criar arquivo .env
cat > .env << 'EOF'
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
EOF

# Deploy via docker-compose
docker-compose up -d --build

# Ver logs
docker-compose logs -f
```

---

### Opção 3: Upload Manual de Arquivos

#### 1. Compactar o projeto

```powershell
# Em PowerShell, compactar toda a pasta
Compress-Archive -Path "c:\Users\gabriel bravo\Desktop\GABRIEL\estagio\Sistema_Protocolo-CGM-main" -DestinationPath "sistema-protocolo.zip" -Force
```

#### 2. Fazer upload via SFTP/FTP

Use FileZilla, WinSCP ou similar para fazer upload do arquivo para o servidor:
- Host: `172.16.32.198`
- Porta SFTP: `22` ou FTP: `21`
- Usuário/Senha SSH

#### 3. Extrair no servidor

```bash
ssh usuario@172.16.32.198

# Navegar para pasta de volumes do Portainer (ou outra pasta)
cd /data/compose

# Extrair
unzip sistema-protocolo.zip

cd Sistema_Protocolo-CGM-main

# Criar .env
nano .env  # Adicionar variáveis

# Deploy
docker-compose up -d --build
```

---

### Opção 4: Usar Portainer com Upload

1. **No Portainer**: Stacks → Add Stack
2. **Nome**: `sistema_protocolo`
3. **Build method**: Escolha **"Upload"**
4. **Upload do arquivo**: Upload do arquivo zip do projeto
5. **Configurar variáveis** como na Opção 1
6. **Deploy**

---

## 🎯 Qual Método Usar?

| Método | Quando Usar | Dificuldade |
|--------|-------------|------------|
| **Git Repository** | Seu código está no Git | ⭐ Fácil |
| **Terminal/SSH** | Você tem acesso SSH | ⭐⭐ Médio |
| **Upload Manual** | Você não tem Git | ⭐⭐⭐ Difícil |

---

## ✅ Recomendação

**Use a Opção 1 (Git Repository)** porque:
- ✅ Mais fácil de manter
- ✅ Atualizações automáticas
- ✅ Backups automáticos
- ✅ Melhor para produção

---

## 📞 Próximo Passo

Você tem algumas opções:

**A) Se você TEM acesso Git**: Use a Opção 1
**B) Se você TEM acesso SSH**: Use a Opção 2
**C) Se você NÃO TEM Git nem SSH**: Use a Opção 4 (Upload)

Qual você prefere? Posso ajudar no próximo passo!

