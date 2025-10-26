#!/bin/bash

echo "============================================"
echo "  Migração Rápida de Dados - Supabase"
echo "============================================"
echo ""

# Verificar se .env existe
if [ ! -f .env ]; then
    echo "❌ Arquivo .env não encontrado!"
    echo "Execute primeiro: cp env.example .env"
    exit 1
fi

# Carregar variáveis do .env
source .env

echo "📦 Este script irá ajudá-lo a migrar dados do Supabase"
echo ""

# Escolher método de migração
echo "Escolha o método de migração:"
echo "1) Via arquivo SQL (.sql)"
echo "2) Via arquivo JSON (Django dumpdata)"
echo "3) Via pg_dump direto"
echo ""
read -p "Escolha uma opção (1-3): " opcao

case $opcao in
    1)
        echo ""
        echo "📝 Migração via SQL"
        read -p "Digite o caminho do arquivo SQL: " arquivo
        if [ -f "$arquivo" ]; then
            echo "Importando $arquivo..."
            docker exec -i protocolo_db psql -U protocolo_user -d protocolo_db < "$arquivo"
            echo "✅ Migração concluída!"
        else
            echo "❌ Arquivo não encontrado: $arquivo"
        fi
        ;;
    2)
        echo ""
        echo "📝 Migração via JSON"
        read -p "Digite o caminho do arquivo JSON: " arquivo
        if [ -f "$arquivo" ]; then
            echo "Copiando $arquivo para o container..."
            docker cp "$arquivo" protocolo_web:/app/temp_backup.json
            echo "Importando dados..."
            docker exec -it protocolo_web python manage.py loaddata /app/temp_backup.json
            docker exec protocolo_web rm /app/temp_backup.json
            echo "✅ Migração concluída!"
        else
            echo "❌ Arquivo não encontrado: $arquivo"
        fi
        ;;
    3)
        echo ""
        echo "📝 Migração via pg_dump direto"
        read -p "Digite o host do Supabase: " SUPABASE_HOST
        read -p "Digite o port do Supabase (padrão 5432): " SUPABASE_PORT
        read -p "Digite o user do Supabase: " SUPABASE_USER
        read -p "Digite o database do Supabase: " SUPABASE_DB
        read -sp "Digite a senha do Supabase: " SUPABASE_PASSWORD
        echo ""
        
        SUPABASE_PORT=${SUPABASE_PORT:-5432}
        
        echo "Exportando do Supabase..."
        PGPASSWORD=$SUPABASE_PASSWORD pg_dump -h $SUPABASE_HOST -p $SUPABASE_PORT -U $SUPABASE_USER -d $SUPABASE_DB > temp_supabase_backup.sql
        
        echo "Importando para banco local..."
        docker exec -i protocolo_db psql -U protocolo_user -d protocolo_db < temp_supabase_backup.sql
        
        echo "Limpando arquivo temporário..."
        rm temp_supabase_backup.sql
        
        echo "✅ Migração concluída!"
        ;;
    *)
        echo "❌ Opção inválida"
        exit 1
        ;;
esac

echo ""
echo "🎉 Pronto! Seus dados foram migrados com sucesso!"
