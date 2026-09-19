#!/usr/bin/env bash
# Backup do banco ANTES de qualquer atualização (item 61).
# Rode no SERVIDOR, na pasta do projeto:   ./backup_banco.sh
# Usa o pg_dump do próprio container do Postgres (mesma versão do servidor).
set -euo pipefail
CONTAINER="${CONTAINER_DB:-protocolo_db}"
USUARIO="${POSTGRES_USER:-protocolo_user}"
BANCO="${POSTGRES_DB:-protocolo_db}"
mkdir -p backups
ARQUIVO="backups/protocolo_$(date +%Y%m%d_%H%M%S).dump"
docker exec "$CONTAINER" pg_dump -U "$USUARIO" -d "$BANCO" -Fc > "$ARQUIVO"
TAMANHO=$(stat -c%s "$ARQUIVO")
if [ "$TAMANHO" -lt 1024 ]; then
  echo "ERRO: backup com ${TAMANHO} bytes — verifique antes de prosseguir." >&2
  exit 1
fi
echo "Backup gravado em $ARQUIVO (${TAMANHO} bytes)."
echo "Para restaurar: docker exec -i $CONTAINER pg_restore -U $USUARIO -d $BANCO --clean --if-exists < $ARQUIVO"
