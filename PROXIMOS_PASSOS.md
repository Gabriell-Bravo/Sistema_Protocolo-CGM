# 🚀 Próximos Passos para Deploy no Portainer

## ✅ Arquivo .env Criado!

Seu arquivo `.env` foi criado com as configurações do seu backup. As seguintes configurações estão prontas:

- **Banco de dados**: protocolo_db (ajustado de "Postgrees")
- **Usuário do banco**: Controladoria
- **Senha do banco**: Cgmroot
- **Porta**: 5432 (ajustada de 5439)
- **Superusuário**: admin
- **Email**: gabrielbravo4321@gmail.com

## 📋 Opções de Deploy

### Opção 1: Via Portainer (Web Interface) ⭐ Recomendado

1. **Acesse o Portainer**
   - Entre no navegador e acesse seu servidor Portainer

2. **Ir para Stacks**
   - No menu lateral, clique em **Stacks**
   - Clique em **Add Stack**

3. **Configurar Stack**
   - Escolha **Web editor**
   - Abra o arquivo `portainer-stack.yml` no seu projeto
   - Copie todo o conteúdo e cole no editor do Portainer

4. **Adicionar Environment Variables**
   - Role até a seção **Environment variables**
   - Adicione cada variável do arquivo `.env`:
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
     POSTGRES_PORT=5432
     TZ=America/Sao_Paulo
     ```

5. **Deploy**
   - Defina um nome para a stack (ex: "sistema-protocolo")
   - Clique em **Deploy the stack**

6. **Aguardar**
   - O Portainer irá fazer o build e iniciar os containers
   - Isso pode levar alguns minutos

### Opção 2: Via Docker Compose (Terminal)

Se você tem acesso SSH ao servidor:

```powershell
# Navegar até a pasta do projeto
cd "c:\Users\gabriel bravo\Desktop\GABRIEL\estagio\Sistema_Protocolo-CGM-main"

# Executar deploy
docker-compose up -d --build

# Ver logs (em outra janela do terminal)
docker-compose logs -f
```

## 🗄️ Migrar Dados do Supabase

Após o deploy funcionar, você precisa migrar os dados:

### Método 1: Backup SQL do Supabase

1. **Exportar dados do Supabase**
   - Acesse o painel do Supabase
   - Vá em Database → Backups
   - Faça download do backup SQL

2. **Importar no banco local**
   ```powershell
   docker exec -i protocolo_db psql -U Controladoria -d protocolo_db < backup.sql
   ```

### Método 2: Via Script Automatizado

```powershell
# Dar permissão ao script (se estiver no Linux/WSL)
chmod +x migracao_rapida.sh

# Executar o script
./migracao_rapida.sh
```

### Método 3: Usando Django dumpdata

Se você tem acesso ao sistema antigo com Supabase:

```bash
# Exportar do Supabase
python manage.py dumpdata > supabase_backup.json

# Importar no banco local
docker cp supabase_backup.json protocolo_web:/app/supabase_backup.json
docker exec -it protocolo_web python manage.py loaddata supabase_backup.json
```

## ✅ Verificar Deploy

Após o deploy:

1. **Acesse a aplicação**
   - URL: `http://seu-servidor:8800`
   - Admin: `http://seu-servidor:8800/admin`

2. **Login**
   - Usuário: `admin`
   - Senha: `burgess-scrapes-traitors-sulus`

3. **Verificar dados**
   - Entre no admin
   - Verifique se os processos foram migrados
   - Verifique se os usuários foram migrados

## 🔧 Comandos Úteis

```powershell
# Ver logs da aplicação
docker logs protocolo_web

# Ver logs do banco
docker logs protocolo_db

# Ver status dos containers
docker ps

# Parar containers
docker-compose down

# Reiniciar containers
docker-compose restart

# Acessar shell Django
docker exec -it protocolo_web python manage.py shell

# Fazer backup
docker exec protocolo_db pg_dump -U Controladoria protocolo_db > backup.sql
```

## 🆘 Problemas Comuns

### Container não inicia
```powershell
# Ver logs detalhados
docker logs protocolo_web
docker logs protocolo_db
```

### Erro de conexão com banco
```powershell
# Verificar se o banco está respondendo
docker exec protocolo_db pg_isready -U Controladoria

# Acessar o banco diretamente
docker exec -it protocolo_db psql -U Controladoria -d protocolo_db
```

### Resetar tudo (cuidado: apaga dados!)
```powershell
docker-compose down -v
docker-compose up -d --build
```

## 📞 Próximos Passos

1. ✅ Arquivo .env criado
2. ⏭️ Fazer deploy no Portainer ou via Docker Compose
3. ⏭️ Migrar dados do Supabase
4. ⏭️ Testar a aplicação
5. ⏭️ Configurar backup automático
6. ⏭️ Configurar HTTPS (opcional)

---

**Documentação completa**: Leia `DEPLOY_PORTTAINER.md`
**Guia rápido**: Leia `README_PORTTAINER.md`
**Checklist**: Leia `CHECKLIST_DEPLOY.md`
