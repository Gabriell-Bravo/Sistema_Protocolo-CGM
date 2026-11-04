import csv
import os
import zipfile
from datetime import date
from urllib.parse import quote, urlencode, urlsplit
from django import forms
import uuid
from io import BytesIO
from pathlib import Path
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction, IntegrityError
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from .models import *
from .forms import *
from .permissions import exigir, visiveis
from .arquivos import guardar, validar
from .extracao import extrair
from . import acompanhamento, automacao_falabr, falabr, memorando_docx, navegador_falabr, ponte_extensao, services
from .prazos import somar, marco
from .pdf import gerar_memorando

def privado(view):
    @login_required
    @wraps(view)
    def wrapped(request,*a,**kw):
        response=view(request,*a,**kw)
        response['Cache-Control']='no-store, private'
        response['X-Content-Type-Options']='nosniff'
        return response
    return wrapped

def demanda_para(request, pk): return get_object_or_404(visiveis(request.user), pk=pk)

def tela_form(request, titulo, form, d=None, **extra):
    return render(request,'lai/form.html',dict(titulo=titulo,form=form,d=d,**extra))

def erro(form, exc): form.add_error(None, '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Conflito de gravação. Confira o registro antes de tentar novamente.')

@privado
def dashboard(request):
    qs=visiveis(request.user)
    if request.GET.get('q'): qs=qs.filter(Q(nup__icontains=request.GET['q'])|Q(resumo__icontains=request.GET['q']))
    if request.GET.get('secretaria'): qs=qs.filter(secretaria_id=request.GET['secretaria'])
    if request.GET.get('status'): qs=qs.filter(status=request.GET['status'])
    for field,lookup in [('inicio','cadastro_falabr__gte'),('fim','cadastro_falabr__lte')]:
        if request.GET.get(field):
            try:
                from datetime import date
                qs=qs.filter(**{lookup:date.fromisoformat(request.GET[field])})
            except ValueError: messages.error(request,'Filtro de data inválido.')
    rows=list(qs.prefetch_related('prorrogacoes','alertas','recursos'))
    hoje=timezone.localdate()
    for d in rows: d.risco=marco(d,hoje); d.abertos=d.recursos.filter(encerrado=False).count()
    cards=[('Demandas',len(rows)),('Aguardando secretaria',sum(d.precisa_resposta_interna for d in rows)),
        ('Prazo vencido',sum(not d.encerrada and d.vencimento<hoje for d in rows)),
        ('Em recurso',sum(d.abertos>0 for d in rows))]
    return render(request,'lai/dashboard.html',dict(rows=rows,cards=cards,secretarias=Secretaria.objects.all(),status=Demanda.STATUS,
        monitor=ExecucaoMonitor.objects.last(),live=settings.LAI_LIVE_EMAIL,
        distribuicao=qs.values('secretaria__nome').annotate(total=Count('pk')).order_by('-total'),
        quantidade_envios=Comunicacao.objects.filter(memorando__demanda__in=qs).count()))

@privado
def pendentes(request):
    exigir(request.user, 'operar')
    erro = None
    if request.method == 'POST':
        acao = request.POST.get('acao')
        if acao == 'tema':
            pk = request.POST.get('pk', '')
            tema = ' '.join((request.POST.get('tema') or '').split())[:200]
            if pk.isdigit() and ManifestacaoFalabr.objects.filter(pk=pk).update(tema=tema):
                messages.success(request, 'Tema atualizado. Ele vale para a próxima vez que a pasta for criada ou conferida.')
            else:
                messages.error(request, 'Pedido não encontrado.')
            filtro_volta = acompanhamento.filtro_valido(request.POST.get('filtro'))
            busca_volta = (request.POST.get('q') or '').strip()[:80]
            return redirect(reverse('lai:pendentes') + '?' + urlencode({'filtro': filtro_volta, 'q': busca_volta}))
        erro = 'Ação desconhecida.'
    registros = list(ManifestacaoFalabr.objects.all())
    if not registros and falabr.configurado():
        try:
            registros = falabr.listar_pendentes()
        except falabr.FalabrError as exc:
            erro = erro or str(exc)
    todos = acompanhamento.montar_lista(registros, visiveis(request.user))
    filtro = acompanhamento.filtro_valido(request.GET.get('filtro'))
    busca = (request.GET.get('q') or '').strip()[:80]
    rows = acompanhamento.filtrar(todos, filtro, busca)
    hoje = timezone.localdate()
    ultimos = {}
    for m in MemorandoFalabr.objects.filter(manifestacao_id__in=[r['pk'] for r in rows if r['pk']]):
        ultimos.setdefault(m.manifestacao_id, m)  # a ordem da classe já traz o mais novo primeiro
    for r in rows:
        r['ultimo_memorando'] = ultimos.get(r['pk'])
        r['memo_obs'] = memorando_docx.observacao_padrao(r['prazo'], hoje, r['prorrogada']) if r['pk'] else 'nenhuma'
    ultimo_numero = (MemorandoFalabr.objects.filter(ano=hoje.year).order_by('-numero')
                     .values_list('numero', flat=True).first()) or 0
    secretarias_memo = list(Secretaria.objects.filter(ativa=True).values_list('nome', flat=True))
    return render(request, 'lai/pendentes.html', {
        'memo_proximo': ultimo_numero + 1, 'memo_hoje': hoje, 'secretarias_memo': secretarias_memo,
        'rows': rows, 'cards': acompanhamento.resumo(todos), 'erro': erro,
        'versao_extensao': ponte_extensao.VERSAO, 'base_guardada': navegador_falabr._base_guardada(),
        'planilha_ativa': bool(getattr(settings, 'LAI_PLANILHA_ATIVA', False)),
        'pode_abrir_pasta': _acesso_local(request), 'pasta_pedidos': str(automacao_falabr.pasta_base()),
        'proxima_numeracao': ponte_extensao.proxima_numeracao(),
        'filtro': filtro, 'busca': busca, 'filtros': acompanhamento.FILTROS,
        'filtro_rotulo': dict((c, r) for c, r, _f in acompanhamento.FILTROS)[filtro],
        'total_lido': len(todos),
        'ultima_leitura': max((r['lida_em'] for r in todos if r['lida_em']), default=None),
    })

def _origem_do_sistema(request):
    """Endereço (https://servidor) que a extensão vai usar. Atrás de proxy, o esquema pode chegar como http."""
    publica = urlsplit(getattr(settings, 'LAI_PUBLIC_URL', '') or '')
    host = request.get_host()
    if publica.scheme and publica.netloc == host:
        return f'{publica.scheme}://{publica.netloc}'
    encaminhado = (request.headers.get('X-Forwarded-Proto') or '').split(',')[0].strip()
    esquema = encaminhado or ('https' if request.is_secure() else 'http')
    return f'{esquema}://{host}'

@privado
def extensao(request):
    """Como instalar a extensão do navegador e o botão para baixá-la."""
    exigir(request.user, 'operar')
    return render(request, 'lai/extensao.html', {'versao': ponte_extensao.VERSAO, 'origem': _origem_do_sistema(request)})

@privado
def extensao_baixar(request):
    """ZIP da extensão já apontando para este sistema e com o código de quem baixa."""
    exigir(request.user, 'operar')
    pacote = ponte_extensao.montar_pacote(_origem_do_sistema(request), request.user)
    resposta = HttpResponse(pacote, content_type='application/zip')
    resposta['Content-Disposition'] = 'attachment; filename="lai-cgm-extensao.zip"'
    return resposta

@privado
def trazer_iniciar(request):
    """A tela vai pedir à extensão que leia o Fala.BR; aqui nasce o andamento que ela acompanha."""
    exigir(request.user, 'operar')
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Use o botão da tela.'}, status=405)
    try:
        dados = ponte_extensao.iniciar_trazer()
    except ponte_extensao.ExtensaoError as exc:
        return JsonResponse({'ok': False, 'erro': str(exc)}, status=409)
    return JsonResponse(dict(dados, ok=True))

@privado
def automacao_iniciar(request):
    exigir(request.user, 'operar')
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Use o botão da tela.'}, status=405)
    ids = [int(x) for x in request.POST.getlist('selecionados') if x.isdigit()][:200]
    if not ids:
        return JsonResponse({'ok': False, 'erro': 'Marque ao menos um pedido na lista.'}, status=400)
    itens = [{'pk': r.pk, 'nup': r.nup, 'link': r.link, 'tema': r.tema_efetivo, 'tema_manual': bool(r.tema),
              'cadastro': r.cadastro, 'prazo': r.prazo}
             for r in ManifestacaoFalabr.objects.filter(pk__in=ids).order_by('nup')]
    try:
        preparo = ponte_extensao.iniciar_pastas(itens, request.POST.get('sequencia_inicial'))
    except ponte_extensao.ExtensaoError as exc:
        return JsonResponse({'ok': False, 'erro': str(exc)}, status=409)
    return JsonResponse(dict(preparo, ok=True))

@privado
def memorandos_gerar(request):
    """Gera o memorando de reiteração (.docx) dos NUPs marcados. Um NUP: o .docx; vários: um .zip."""
    exigir(request.user, 'operar')
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Use o botão da tela.'}, status=405)
    pks = request.POST.getlist('pk')
    if not pks or len(pks) > 100:
        return JsonResponse({'ok': False, 'erro': 'Marque de 1 a 100 pedidos para gerar os memorandos.'}, status=400)
    campos = {nome: request.POST.getlist(nome) for nome in ('numero', 'secretaria', 'tratamento', 'prazo', 'observacao')}
    if any(len(v) != len(pks) for v in campos.values()):
        return JsonResponse({'ok': False, 'erro': 'Os dados dos memorandos vieram incompletos. Abra a janela de novo.'}, status=400)
    try:
        data = date.fromisoformat(request.POST.get('data') or '')
    except ValueError:
        return JsonResponse({'ok': False, 'erro': 'Informe a data do memorando.'}, status=400)
    registros = {str(r.pk): r for r in ManifestacaoFalabr.objects.filter(pk__in=[p for p in pks if p.isdigit()])}
    arquivos, historico, numeros = [], [], set()
    for i, pk in enumerate(pks):
        registro = registros.get(pk)
        if registro is None:
            return JsonResponse({'ok': False, 'erro': 'Um dos pedidos marcados não existe mais. Atualize a lista.'}, status=400)
        try:
            prazo = date.fromisoformat(campos['prazo'][i])
        except ValueError:
            return JsonResponse({'ok': False, 'erro': f'NUP {registro.nup}: informe o prazo da resposta.'}, status=400)
        try:
            conteudo = memorando_docx.gerar(
                numero=campos['numero'][i], data=data, nup=registro.nup, secretaria=campos['secretaria'][i],
                prazo=prazo, tratamento=campos['tratamento'][i], observacao=campos['observacao'][i])
        except memorando_docx.MemorandoError as exc:
            return JsonResponse({'ok': False, 'erro': f'NUP {registro.nup}: {exc}'}, status=400)
        numero = int(campos['numero'][i])
        if numero in numeros:
            return JsonResponse({'ok': False, 'erro': f'O número {numero} foi usado em mais de um memorando desta remessa.'}, status=400)
        numeros.add(numero)
        arquivos.append((memorando_docx.nome_do_arquivo(numero, data.year, registro.nup), conteudo))
        historico.append(MemorandoFalabr(
            manifestacao=registro, numero=numero, ano=data.year, data=data, prazo=prazo, usuario=request.user,
            secretaria=' '.join(campos['secretaria'][i].split())))
    MemorandoFalabr.objects.bulk_create(historico)
    if len(arquivos) == 1:
        nome, conteudo = arquivos[0]
        resposta = HttpResponse(conteudo, content_type=(
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'))
        nome_zip = nome
    else:
        pacote = BytesIO()
        with zipfile.ZipFile(pacote, 'w', zipfile.ZIP_DEFLATED) as z:
            for nome, conteudo in arquivos:
                z.writestr(nome, conteudo)
        resposta = HttpResponse(pacote.getvalue(), content_type='application/zip')
        nome_zip = f'memorandos-lai-{data.isoformat()}.zip'
    resposta['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(nome_zip)
    return resposta

@privado
def automacao_cancelar(request):
    exigir(request.user, 'operar')
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Use o botão da tela.'}, status=405)
    ponte_extensao.cancelar((request.POST.get('motivo') or 'Cancelado.')[:300])
    return JsonResponse({'ok': True})

@privado
def automacao_zip(request):
    """Baixa, num ZIP, as pastas dos pedidos da última tarefa (a pasta fica no servidor)."""
    exigir(request.user, 'operar')
    if not ponte_extensao.pastas_da_tarefa():
        return HttpResponse('Nenhuma pasta pronta para baixar.', status=404, content_type='text/plain; charset=utf-8')
    caminho = ponte_extensao.zip_das_pastas()
    arquivo = open(caminho, 'rb')

    class _ApagaDepois(FileResponse):
        def close(self):
            super().close()
            try:
                os.unlink(caminho)
            except OSError:
                pass
    resposta = _ApagaDepois(arquivo, as_attachment=True, filename='pastas-lai.zip', content_type='application/zip')
    return resposta

def _acesso_local(request):
    """Abrir pasta só faz sentido quando quem clica está no mesmo computador do sistema (Windows)."""
    return os.name == 'nt' and request.META.get('REMOTE_ADDR') in ('127.0.0.1', '::1')

@privado
def automacao_estado(request):
    exigir(request.user, 'operar')
    dados = ponte_extensao.estado()
    dados['pode_abrir_pasta'] = _acesso_local(request)
    dados['pode_baixar_zip'] = bool(ponte_extensao.pastas_da_tarefa()) and not dados.get('rodando')
    return JsonResponse(dados)

@privado
def automacao_abrir_pasta(request):
    exigir(request.user, 'operar')
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Use o botão da tela.'}, status=405)
    if not _acesso_local(request):
        return JsonResponse({'ok': False, 'erro': 'A pasta só abre quando você acessa o sistema pelo próprio computador onde ele roda.'}, status=403)
    pasta = automacao_falabr.pasta_base()
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        os.startfile(str(pasta))
    except OSError:
        return JsonResponse({'ok': False, 'erro': 'Não foi possível abrir a pasta.'}, status=500)
    return JsonResponse({'ok': True})

@privado
def exportar_falabr(request):
    exigir(request.user, 'operar')
    filtro = acompanhamento.filtro_valido(request.GET.get('filtro'))
    todos = acompanhamento.montar_lista(ManifestacaoFalabr.objects.all(), visiveis(request.user))
    rows = acompanhamento.filtrar(todos, filtro, (request.GET.get('q') or '').strip()[:80])
    out = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    out['Content-Disposition'] = f'attachment; filename="falabr-{filtro}.csv"'
    out.write('\ufeff')
    w = csv.writer(out, delimiter=';')
    w.writerow(['NUP', 'Tipo', 'Assunto', 'Cadastro', 'Prazo', 'Dias', 'Faixa', 'Situação no Fala.BR',
                'Responsável', 'No módulo', 'Avisos'])
    def safe(v):
        s = '' if v is None else str(v)
        return "'" + s if s.lstrip().startswith(('=', '+', '-', '@')) else s
    for i in rows:
        w.writerow([safe(v) for v in [
            i['nup'], i['tipo'], i['assunto'],
            i['cadastro'].strftime('%d/%m/%Y') if i['cadastro'] else '',
            i['prazo'].strftime('%d/%m/%Y') if i['prazo'] else '',
            i['dias_texto'], i['faixa'], i['situacao'], i['responsavel'],
            i['demanda'].get_status_display() if i['demanda'] else 'Não cadastrada',
            ' '.join(i['avisos'])]])
    return out

@privado
def importar(request, pk=None):
    d=demanda_para(request,pk) if pk else None
    exigir(request.user,'operar',d)
    form=UploadForm(request.POST or None,request.FILES or None)
    if request.method=='POST' and form.is_valid():
        try:
            upload=form.cleaned_data['arquivo']
            data,ext=validar(upload)
            if ext!='.pdf': raise ValidationError('Envie PDF da NUP.')
            result=extrair(BytesIO(data))
            imp=Importacao(usuario=request.user,nome=Path(upload.name).name,dados=result)
            imp.arquivo.save(f'{uuid.uuid4().hex}.pdf',ContentFile(data),save=False); imp.save()
            url=reverse('lai:revisar',args=[d.pk]) if d else reverse('lai:nova')
            return redirect(url+'?importacao='+str(imp.pk))
        except (ValidationError,ValueError) as exc: form.add_error(None,str(exc))
        except Exception: form.add_error(None,'Não foi possível ler o PDF. Use cadastro manual ou uma cópia legível.')
    return tela_form(request,'Reimportar PDF' if d else 'Importar NUP do Fala.BR',form,d,ajuda='O PDF será extraído localmente. Você confere todos os campos antes de confirmar o cadastro.')

@privado
def nova(request, pk=None):
    d=demanda_para(request,pk) if pk else None
    op=exigir(request.user,'operar',d)
    token=request.GET.get('importacao')
    imp=get_object_or_404(Importacao,pk=token,usuario=request.user,utilizada=False) if token else None
    initial={}
    lida=None
    if not d and not imp and request.GET.get('falabr','').isdigit():
        lida=ManifestacaoFalabr.objects.filter(pk=request.GET['falabr']).first()
        if lida: initial=acompanhamento.dados_iniciais(lida)
    if imp:
        initial={k:v for k,v in imp.dados.items() if k in DemandaForm.Meta.fields}
        initial['marco_inicial']=initial.get('cadastro_falabr')
        initial['prazo_interno']=initial.get('vencimento_original')
        if d and imp.dados.get('nup') and ''.join(filter(str.isdigit,imp.dados['nup']))!=d.nup_normalizada:
            messages.error(request,'O PDF pertence a outra NUP. Reimportação recusada.'); return redirect('lai:detalhe',pk=d.pk)
    if d and d.encerrada:
        messages.error(request,'Demanda encerrada: anexe novos documentos sem alterar a resposta original.'); return redirect('lai:detalhe',pk=d.pk)
    form=DemandaForm(request.POST or None,instance=d,initial=initial)
    form.fields['secretaria'].queryset=Secretaria.objects.filter(ativa=True)
    if not op.acesso_global: form.fields['secretaria'].queryset=op.secretarias.filter(ativa=True)
    if d:
        # Reimportação revisa conteúdo, sem trocar identidade ou reiniciar prazo.
        for f in ['nup','cadastro_falabr','marco_inicial','vencimento_original','prazo_interno','secretaria']:
            form.fields[f].disabled=True
            form.initial[f]=getattr(d,f+'_id',getattr(d,f))
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                if imp:
                    imp=Importacao.objects.select_for_update().get(pk=imp.pk)
                    if imp.utilizada: raise ValidationError('Importação já utilizada.')
                obj=form.save(commit=False)
                if not d:
                    obj.operador=op
                    obj.politica=PoliticaPrazo.objects.order_by('-id').first()
                    if not obj.politica: raise ValidationError('Cadastre uma política de prazo.')
                old = Demanda.objects.filter(pk=obj.pk).values('resumo','teor','status').first() if obj.pk else None
                if d:
                    obj.conferido_em=None; obj.status='CONFERENCIA'
                    Comunicacao.objects.filter(memorando__demanda=d,status='PENDENTE').update(status='CANCELADO')
                if imp: obj.anexos_esperados=imp.dados.get('anexos_esperados',[])
                obj.save()
                if imp:
                    with imp.arquivo.open('rb') as raw:
                        cf=ContentFile(raw.read(),name=imp.nome)
                        guardar(obj,cf,'NUP',request.user,{'extracao':imp.dados})
                    imp.utilizada=True; imp.save()
                services.evento(obj,request.user,'REIMPORTACAO' if d else 'CADASTRO',anterior=old or {},novo={'resumo':obj.resumo,'teor':obj.teor},origem='PDF' if imp else 'MANUAL')
            return redirect('lai:detalhe',pk=obj.pk)
        except (ValidationError,IntegrityError) as exc: erro(form,exc)
    return tela_form(request,'Conferir dados da NUP' if imp else 'Cadastro manual' if not d else 'Revisar demanda',form,d,
        imp=imp,avisos=imp.dados.get('avisos',[]) if imp else [],
        ajuda='NUP, tipo, datas e prazo vieram da lista do Fala.BR. Escolha a secretaria e cole o teor integral do pedido antes de salvar. O prazo do Fala.BR é preservado.' if lida else 'Salvar mantém a demanda aguardando conferência. O prazo do Fala.BR é preservado.')

@privado
def detalhe(request,pk):
    d=demanda_para(request,pk)
    expected=d.anexos_esperados
    actual=set(d.documentos.values_list('nome',flat=True))
    calculado=somar(d.marco_inicial,20,d.politica)
    return render(request,'lai/detalhe.html',dict(d=d,calculado=calculado,divergente=calculado!=d.vencimento_original,
        faltantes=[n for n in expected if n not in actual],risco=marco(d,timezone.localdate()),
        documentos=d.documentos.order_by('-criado_em'),memorandos=d.memorandos.all(),eventos=d.eventos.select_related('usuario')[:100],
        recursos=d.recursos.prefetch_related('etapas'),prorrogacoes=d.prorrogacoes.all(),respostas=d.respostas.all()))

@privado
def acao(request,pk,tipo):
    d=demanda_para(request,pk)
    specs={'confirmar':(ConfirmarForm,'operar','Confirmar conferência'), 'anexo':(AnexoForm,'operar','Adicionar documento'),
        'memorando':(MemorandoForm,'expedir','Revisar e emitir memorando'),'prorrogar':(ProrrogacaoForm,'prorrogar','Formalizar prorrogação'),
        'resposta':(RespostaForm,'operar','Registrar resposta'),'recurso':(RecursoForm,'recorrer','Cadastrar recurso'),
        'redirecionar':(RedirecionarForm,'operar','Redirecionar internamente'),'automacao':(AutomacaoForm,'expedir','Configurar cobranças automáticas'),
        'arquivar':(MotivoForm,'operar','Arquivar demanda respondida')}
    if tipo not in specs: return HttpResponse(status=404)
    cls,perm,title=specs[tipo]; op=exigir(request.user,perm,d)
    initial={}
    if tipo=='memorando':
        try: initial['texto']=services.minuta(d)[1]
        except ValidationError as exc: messages.error(request,str(exc))
    if tipo=='automacao': initial={'auto_cobranca':d.auto_cobranca,'autorizacao_automacao':d.autorizacao_automacao}
    if tipo=='prorrogar': initial['novo_prazo']=somar(d.vencimento_original,10,d.politica)
    form=cls(request.POST or None,request.FILES or None,initial=initial)
    for name in ('comprovante','documento'):
        if name in form.fields: form.fields[name].queryset=d.documentos.all()
    if tipo=='redirecionar' and not op.acesso_global: form.fields['secretaria'].queryset=op.secretarias.filter(ativa=True)
    if request.method=='POST' and form.is_valid():
        try:
            data=form.cleaned_data
            with transaction.atomic():
                if tipo=='confirmar': services.confirmar(d,request.user,**data)
                elif tipo=='anexo':
                    doc=guardar(d,data['arquivo'],data['categoria'],request.user)
                    services.evento(d,request.user,'DOCUMENTO_ADICIONADO',documento=str(doc.pk),categoria=doc.categoria)
                elif tipo=='memorando': services.emitir(d,request.user,**data)
                elif tipo=='prorrogar': services.prorrogar(d,request.user,**data)
                elif tipo=='resposta': services.responder(d,request.user,**data)
                elif tipo=='recurso': services.criar_recurso(d,request.user,**data)
                elif tipo=='redirecionar': services.redirecionar(d,request.user,**data)
                elif tipo=='automacao':
                    d.auto_cobranca=data['auto_cobranca']; d.autorizacao_automacao=data['autorizacao_automacao']; d.save()
                    services.evento(d,request.user,'AUTOMACAO',**data)
                elif tipo=='arquivar':
                    if d.status!='RESPONDIDA' or d.recursos.filter(encerrado=False).exists(): raise ValidationError('Responda no Fala.BR e conclua os recursos antes de arquivar.')
                    d.status='ARQUIVADA'; d.save(); services.evento(d,request.user,'ARQUIVAMENTO',**data)
            messages.success(request,'Registro salvo no histórico.'); return redirect('lai:detalhe',pk=d.pk)
        except (ValidationError,IntegrityError) as exc: erro(form,exc)
    return tela_form(request,title,form,d)

@privado
def etapa(request,recurso_id):
    r=get_object_or_404(Recurso,pk=recurso_id,demanda__in=visiveis(request.user)); exigir(request.user,'recorrer',r.demanda)
    form=EtapaForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:
            services.nova_etapa(r,request.user,**form.cleaned_data); return redirect('lai:detalhe',pk=r.demanda_id)
        except ValidationError as exc: erro(form,exc)
    return tela_form(request,'Abrir etapa do recurso',form,r.demanda,ajuda='Comissão e hipóteses sem prazo expresso precisam de fundamento específico. A consulta jurídica não suspende outros prazos automaticamente.')

@privado
def decisao(request,etapa_id,prazo=False):
    e=get_object_or_404(EtapaRecurso,pk=etapa_id,recurso__demanda__in=visiveis(request.user)); exigir(request.user,'decidir',e.recurso.demanda)
    form=(PrazoEtapaForm if prazo else DecisaoForm)(request.POST or None)
    if not prazo: form.fields['documento_decisao'].queryset=e.recurso.demanda.documentos.all()
    if request.method=='POST' and form.is_valid():
        try:
            (services.prazo_etapa if prazo else services.decidir)(e,request.user,**form.cleaned_data)
            return redirect('lai:detalhe',pk=e.recurso.demanda_id)
        except ValidationError as exc: erro(form,exc)
    return tela_form(request,'Ajustar prazo da etapa' if prazo else 'Registrar decisão e comunicação',form,e.recurso.demanda)

@privado
def encerrar_recurso(request,recurso_id):
    r=get_object_or_404(Recurso,pk=recurso_id,demanda__in=visiveis(request.user)); exigir(request.user,'decidir',r.demanda)
    form=MotivoForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        if not r.etapas.exists() or r.etapas.filter(decidida_em=None).exists(): form.add_error(None,'Conclua as etapas e registre comunicação antes de encerrar.')
        elif r.etapas.exclude(instancia='PROCURADORIA').last().resultado in ('PROVIDO','PARCIAL'):
            form.add_error(None,'A decisão exige providências: registre a etapa de cumprimento antes de encerrar.')
        else:
            r.encerrado=True; r.save(); services.evento(r.demanda,request.user,'RECURSO_ENCERRADO',recurso=r.pk,**form.cleaned_data)
            return redirect('lai:detalhe',pk=r.demanda_id)
    return tela_form(request,'Encerrar acompanhamento do recurso',form,r.demanda)

@privado
def documento(request,doc_id):
    doc=get_object_or_404(Documento,pk=doc_id,demanda__in=visiveis(request.user))
    services.evento(doc.demanda,request.user,'DOCUMENTO_ACESSADO',documento=str(doc.pk))
    return FileResponse(doc.arquivo.open('rb'),as_attachment=True,filename=doc.nome)

@privado
@xframe_options_sameorigin
def original_importacao(request,imp_id):
    exigir(request.user,'operar')
    imp=get_object_or_404(Importacao,pk=imp_id,usuario=request.user)
    return FileResponse(imp.arquivo.open('rb'),content_type='application/pdf')

@privado
def memorando_pdf(request,memo_id):
    m=get_object_or_404(Memorando,pk=memo_id,demanda__in=visiveis(request.user))
    services.evento(m.demanda,request.user,'MEMORANDO_ACESSADO',memorando=m.pk)
    return FileResponse(BytesIO(gerar_memorando(m)),as_attachment=True,filename=f'memorando-{m.ano}-{m.numero}.pdf')

@privado
def memorando_acao(request,memo_id,tipo):
    if tipo not in ('assinatura','cancelar'): return HttpResponse(status=404)
    m=get_object_or_404(Memorando,pk=memo_id,demanda__in=visiveis(request.user)); exigir(request.user,'expedir',m.demanda)
    form=(AssinaturaForm if tipo=='assinatura' else MotivoForm)(request.POST or None)
    if tipo=='assinatura': form.fields['documento'].queryset=m.demanda.documentos.filter(categoria='ASSINADO')
    if request.method=='POST' and form.is_valid():
        if tipo=='assinatura':
            m.documento_assinado=form.cleaned_data['documento']; m.metodo_assinatura=form.cleaned_data['metodo']; m.save()
            services.evento(m.demanda,request.user,'ASSINATURA_REGISTRADA',memorando=m.pk,metodo=m.metodo_assinatura)
        else:
            m.cancelado=True; m.motivo_cancelamento=form.cleaned_data['motivo']; m.save()
            m.comunicacoes.filter(status='PENDENTE').update(status='CANCELADO')
            services.evento(m.demanda,request.user,'MEMORANDO_CANCELADO',memorando=m.pk,**form.cleaned_data)
        return redirect('lai:detalhe',pk=m.demanda_id)
    return tela_form(request,'Vincular documento assinado' if tipo=='assinatura' else 'Cancelar memorando',form,m.demanda)

@privado
def reconciliar(request,com_id):
    c=get_object_or_404(Comunicacao,pk=com_id,memorando__demanda__in=visiveis(request.user)); exigir(request.user,'expedir',c.memorando.demanda)
    form=EnvioForm(request.POST or None); form.fields['comprovante'].queryset=c.memorando.demanda.documentos.all()
    if request.method=='POST' and form.is_valid():
        if c.status=='PROCESSANDO': form.add_error(None,'Envio em processamento. Aguarde a conclusão ou recuperação do monitor.')
        elif c.memorando.cancelado: form.add_error(None,'Memorando cancelado.')
        else:
            c.status='MANUAL' if form.cleaned_data['acao']=='MANUAL' else 'PENDENTE'
            c.comprovante=form.cleaned_data['comprovante']; c.save()
            services.evento(c.memorando.demanda,request.user,'ENVIO_RECONCILIADO',comunicacao=c.pk,acao=form.cleaned_data['acao'],motivo=form.cleaned_data['motivo'])
            return redirect('lai:detalhe',pk=c.memorando.demanda_id)
    return tela_form(request,'Reconciliação de envio',form,c.memorando.demanda,ajuda='Confira a caixa institucional antes de autorizar nova tentativa. Anexe evidência da verificação ou do envio manual.')

@privado
def gestao(request):
    exigir(request.user,'gestao')
    ds=list(visiveis(request.user))
    rows=[]
    for d in ds:
        risk=marco(d,timezone.localdate())
        alerts=list(d.alertas.filter(ativo=True))
        if risk or alerts:
            rows.append({'d':d,'risco':risk,'alertas':alerts,'ultimo':d.memorandos.first()})
    return render(request,'lai/gestao.html',{'rows':rows,'monitor':ExecucaoMonitor.objects.last()})

@privado
def exportar(request):
    exigir(request.user,'gestao')
    out=HttpResponse(content_type='text/csv; charset=utf-8-sig'); out['Content-Disposition']='attachment; filename="lai-demandas.csv"'
    out.write('\ufeff'); w=csv.writer(out,delimiter=';'); w.writerow(['NUP','Secretaria','Cadastro','Vencimento','Situação','Em recurso'])
    def safe(v):
        s=str(v); return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
    for d in visiveis(request.user): w.writerow([safe(v) for v in [d.nup,d.secretaria.nome,d.cadastro_falabr,d.vencimento,d.get_status_display(),d.recursos.filter(encerrado=False).exists()]])
    return out

CADASTROS={'secretarias':(Secretaria,['nome','sigla','email','responsavel','substituto','ativa','referencia_externa']),
    'operadores':(Operador,['usuario','nome','cargo','matricula','unidade','email','ativo','secretarias','acesso_global','autoridade_recursal']),
    'politicas':(PoliticaPrazo,['versao','dias_uteis','ajustar_vencimento','feriados','homologada','fundamento','alerta_inicial','alerta_urgente','alerta_prorrogacao']),
    'modelos':(ModeloMemorando,['versao','texto','ativo'])}

@privado
def cadastros(request):
    exigir(request.user,'cadastrar')
    return render(request,'lai/cadastros.html',{'grupos':[{'slug':slug,'nome':slug.title(),'itens':model.objects.all()} for slug,(model,_) in CADASTROS.items()]})

@privado
def cadastro(request,slug,pk=None):
    exigir(request.user,'cadastrar')
    if slug not in CADASTROS: return HttpResponse(status=404)
    model,fields=CADASTROS[slug]
    obj=get_object_or_404(model,pk=pk) if pk else None
    cls=forms.modelform_factory(model,form=BaseForm,fields=fields)
    form=cls(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        try:
            if slug=='politicas' and obj and obj.demandas.exists(): raise ValidationError('Política em uso. Crie nova versão.')
            obj=form.save()
            from django.contrib.admin.models import LogEntry, CHANGE, ADDITION
            from django.contrib.contenttypes.models import ContentType
            LogEntry.objects.log_actions(user_id=request.user.pk,queryset=model.objects.filter(pk=obj.pk),action_flag=CHANGE if pk else ADDITION,change_message='Cadastro LAI atualizado pela interface de configuração.')
            return redirect('lai:cadastros')
        except ValidationError as exc: erro(form,exc)
    return tela_form(request,('Editar ' if pk else 'Cadastrar ')+slug,form)
