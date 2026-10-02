from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0030_sem_relatorio'),
    ]

    operations = [
        migrations.AddField(
            model_name='processo',
            name='sequencia_relatorio',
            field=models.CharField(
                blank=True,
                default='',
                max_length=50,
                verbose_name='Sequência de relatório (ajuste do administrador)',
            ),
        ),
    ]
