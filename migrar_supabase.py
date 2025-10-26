"""
Script para migração de dados do Supabase para PostgreSQL local
Execute este script após configurar as credenciais do Supabase
"""

from django.contrib.auth.models import User
from processos_app.models import Processo, ProcessHistory, MonitoramentoRecord, Profile
import os
import sys
import django
from django.db import connection

# Configurar ambiente Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'protocolo_project.settings')
django.setup()


def migrar_dados():
    """
    Esta função é um template para migração de dados do Supabase.

    Você precisa:
    1. Instalar psycopg2-binary e django: pip install psycopg2-binary django
    2. Configurar as variáveis de ambiente do Supabase
    3. Executar este script para migrar os dados
    """

    print("=" * 60)
    print("Script de Migração de Dados - Supabase para PostgreSQL Local")
    print("=" * 60)

    # Verificar se há dados no banco local
    total_processos = Processo.objects.count()
    total_users = User.objects.count()

    print(f"\nEstatísticas do Banco Local:")
    print(f"  - Processos: {total_processos}")
    print(f"  - Usuários: {total_users}")

    # TODO: Implementar lógica de migração baseada nas suas necessidades
    print("\nPara migrar dados do Supabase:")
    print("1. Exporte os dados do Supabase em formato SQL ou CSV")
    print("2. Use o painel do Supabase ou ferramentas como pgAdmin para exportar")
    print("3. Execute os seguintes comandos:")
    print("\n   # Para migração via SQL:")
    print("   docker exec -i protocolo_db psql -U protocolo_user -d protocolo_db < backup.sql")
    print("\n   # Para importação manual, use o Django shell:")
    print("   docker exec -it protocolo_web python manage.py shell")
    print("\n   # No shell, execute:")
    print("   from processos_app.models import Processo")
    print("   # Importe seus dados aqui")

    print("\n" + "=" * 60)
    print("Migração configurada. Verifique os dados no admin.")
    print("=" * 60)


if __name__ == "__main__":
    migrar_dados()
