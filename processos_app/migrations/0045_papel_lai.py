from django.db import migrations, models


class Migration(migrations.Migration):
    """Novo papel LAI: conta dedicada ao módulo de Acesso à Informação."""

    dependencies = [
        ('processos_app', '0044_prioridade_n_recorrente'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='papel',
            field=models.CharField(choices=[('PROTOCOLO', 'Protocolo'), ('ANALISTA_LICITACOES', 'Analista – Licitações e Contratos'), ('ANALISTA_LIQUIDACOES', 'Analista – Liquidações'), ('GESTAO', 'Gestão'), ('LAI', 'LAI – Acesso à Informação')], db_index=True, default='GESTAO', max_length=30, verbose_name='Papel operacional'),
        ),
    ]
