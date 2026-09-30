from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0022_tramite_desfeito'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='linhacontrolerelatorio',
            name='uniq_controle_relatorio_grupo_numero',
        ),
    ]
