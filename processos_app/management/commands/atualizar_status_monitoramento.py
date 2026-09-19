"""Grava o status de monitoramento calculado (item 43).

As telas calculam o status na hora (sem gravar em GET). Este comando só
alinha o campo gravado, para relatórios e exportações. Agendar 1x por dia:

    docker exec protocolo_web python manage.py atualizar_status_monitoramento
"""

from django.core.management.base import BaseCommand

from processos_app.services import monitoramento


class Command(BaseCommand):
    help = 'Atualiza o status de monitoramento gravado (ATRASADO / PENDENTE).'

    def handle(self, *args, **opcoes):
        resultado = monitoramento.persistir_status()
        for status, quantidade in (resultado or {}).items():
            self.stdout.write(f'{status}: {quantidade}')
        self.stdout.write(self.style.SUCCESS('Status de monitoramento atualizado.'))
