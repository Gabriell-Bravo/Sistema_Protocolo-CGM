from django.core.management.base import BaseCommand
from lai.services import monitorar
from lai.emailing import processar_fila
class Command(BaseCommand):
    help='Atualiza alertas e, com --enviar, processa a fila conforme modo configurado.'
    def add_arguments(self, parser): parser.add_argument('--enviar', action='store_true')
    def handle(self,*args,**options):
        monitorar()
        if options['enviar']: self.stdout.write(str(processar_fila()))
        self.stdout.write(self.style.SUCCESS('Monitoramento LAI concluído.'))
