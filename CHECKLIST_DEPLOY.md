# ✅ Checklist de Deploy - Portainer

Use este checklist para garantir que tudo está configurado corretamente antes do deploy.

## 📋 Pré-Deploy

### Ambiente
- [ ] Portainer instalado e acessível
- [ ] Acesso ao servidor via SSH/terminal
- [ ] Python 3.11+ (para testes locais) ou Docker instalado
- [ ] Git configurado (opcional)

### Arquivos
- [ ] Arquivo `env.example` presente
- [ ] Criar arquivo `.env` baseado no `env.example`
- [ ] Configurar todas as variáveis no `.env`

### Configurações do .env
- [ ] `DJANGO_SECRET_KEY` - Gerar chave segura
- [ ] `DJANGO_DEBUG` - Definir como False em produção
- [ ] `DJANGO_SUPERUSER_USERNAME` - Definir usuário admin
- [ ] `DJANGO_SUPERUSER_EMAIL` - Definir email admin
- [ ] `DJANGO_SUPERUSER_PASSWORD` - Definir senha forte
- [ ] `POSTGRES_DB` - Nome do banco
- [ ] `POSTGRES_USER` - Usuário do banco
- [ ] `POSTGRES_PASSWORD` - Senha forte do banco

### Credenciais Supabase (se aplicável)
- [ ] Host do banco Supabase
- [ ] Porta do banco Supabase
- [ ] Usuário do banco Supabase
- [ ] Senha do banco Supabase
- [ ] Nome do banco Supabase

## 🚀 Deploy

### Via Portainer
- [ ] Acessar Portainer
- [ ] Ir em Stacks → Add Stack
- [ ] Colar conteúdo de `portainer-stack.yml`
- [ ] Adicionar variáveis de ambiente
- [ ] Deploy da stack

### Via Terminal
- [ ] Executar `chmod +x setup_portainer.sh`
- [ ] Executar `./setup_portainer.sh`
- [ ] Verificar configurações do `.env`
- [ ] Executar `docker-compose up -d --build`
- [ ] Verificar logs com `docker-compose logs -f`

## 🗄️ Migração de Dados

- [ ] Fazer backup do banco Supabase
- [ ] Executar script de migração OU
- [ ] Importar SQL direto via `pg_dump/psql`
- [ ] Verificar dados importados

### Métodos de Migração

#### Método 1: SQL
- [ ] Exportar backup.sql do Supabase
- [ ] Importar: `docker exec -i protocolo_db psql -U protocolo_user -d protocolo_db < backup.sql`

#### Método 2: Script
- [ ] Executar `chmod +x migracao_rapida.sh`
- [ ] Executar `./migracao_rapida.sh`
- [ ] Seguir instruções interativas

#### Método 3: Django dumpdata
- [ ] Exportar do Supabase: `python manage.py dumpdata > supabase_backup.json`
- [ ] Copiar para container: `docker cp supabase_backup.json protocolo_web:/app/`
- [ ] Importar: `docker exec -it protocolo_web python manage.py loaddata supabase_backup.json`

## ✅ Verificação Pós-Deploy

### Aplicação
- [ ] Acessar `http://seu-servidor:8800` funciona
- [ ] Acessar `http://seu-servidor:8800/admin` funciona
- [ ] Login com credenciais de admin funciona
- [ ] Páginas principais carregam corretamente

### Banco de Dados
- [ ] Dados migrados estão presentes
- [ ] Tabelas criadas corretamente
- [ ] Usuários migrados corretamente
- [ ] Processos migrados corretamente

### Containers
- [ ] Container `protocolo_web` está rodando
- [ ] Container `protocolo_db` está rodando
- [ ] Sem erros nos logs

### Volumes
- [ ] Volume `postgres_data` criado
- [ ] Backup dos arquivos estáticos
- [ ] Backup dos arquivos de mídia

## 🔒 Segurança

### Produção
- [ ] `DJANGO_DEBUG` está como `False`
- [ ] Senhas fortes configuradas
- [ ] Firewall configurado
- [ ] Portas 5432 e 8800 ajustadas conforme necessário
- [ ] SSL/HTTPS configurado (recomendado)

### Backup
- [ ] Backup automático configurado
- [ ] Teste de restore realizado
- [ ] Documentação de backup criada

## 📊 Monitoramento

### Logs
- [ ] Logs da aplicação configurados
- [ ] Logs do banco configurados
- [ ] Alertas configurados (opcional)

### Performance
- [ ] Verificar uso de recursos: `docker stats`
- [ ] Número de workers configurado (padrão: 3)
- [ ] Timeout configurado (padrão: 120s)

## 📝 Documentação

- [ ] Credenciais documentadas (em local seguro)
- [ ] Instruções de acesso documentadas
- [ ] Lista de contatos atualizada
- [ ] README atualizado

## 🎉 Finalização

- [ ] Testar todas as funcionalidades principais
- [ ] Notificar usuários do deploy
- [ ] Criar usuários de teste (opcional)
- [ ] Atualizar documentação de usuário

---

## 🆘 Se algo der errado

### Container não inicia
```bash
docker logs protocolo_web
docker logs protocolo_db
```

### Resetar tudo
⚠️ **CUIDADO - Apaga todos os dados!**
```bash
docker-compose down -v
docker volume rm protocolo_cgm-main_postgres_data
docker-compose up -d --build
```

### Verificar banco
```bash
docker exec -it protocolo_db psql -U protocolo_user -d protocolo_db
```

### Reexecutar migrações
```bash
docker exec -it protocolo_web python manage.py makemigrations
docker exec -it protocolo_web python manage.py migrate
```

---

**Última atualização**: Criado automaticamente
**Próximo deploy**: Verificar atualizações antes do próximo deploy
