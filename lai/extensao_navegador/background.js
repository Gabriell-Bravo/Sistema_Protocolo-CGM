// LAI CGM: ponte entre o sistema e o Fala.BR.
// Roda no navegador de quem usa. Não vê nem guarda senha ou CPF: usa a página do Fala.BR
// que a própria pessoa abriu e entrou com o gov.br, lê o que a tela mostra e envia ao sistema.
importScripts('config.js');

const CFG = self.LAI_CONFIG;
const FALABR = 'https://falabr.cgu.gov.br';
const MODAL = '#modalConfirmacaoDadosManifestante';
const GRUPOS = [['abertas', '1,2,3,4,5'], ['encerradas', '6,7,8']];
const MAX_PAGINAS = 80;
const PEDACO = 3 * 1024 * 1024;

let job = null; // tarefa em andamento: {tipo, cancelar, esperaDownload, baixados, diag}

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------- servidor

async function api(caminho, corpo, formulario) {
  const cabecalhos = { Authorization: 'Bearer ' + CFG.token };
  if (!formulario) cabecalhos['Content-Type'] = 'application/json';
  let resposta;
  try {
    resposta = await fetch(CFG.servidor + '/lai/ext/api/' + caminho, {
      method: 'POST',
      headers: cabecalhos,
      body: formulario || JSON.stringify(corpo || {}),
    });
  } catch (e) {
    throw new Error('Não consegui falar com o sistema (' + CFG.servidor + '). Confira a rede.');
  }
  let json = {};
  try { json = await resposta.json(); } catch (e) { /* sem corpo */ }
  if (!resposta.ok) throw new Error(json.erro || ('O sistema respondeu com erro ' + resposta.status + '.'));
  return json;
}

async function progresso(campos) {
  const r = await api('progresso/', campos);
  if (job && r && r.continuar === false) job.cancelar = true;
  return r;
}

// ------------------------------------------------------------ funções que rodam DENTRO da página

function paginaLerUsuario() {
  const botao = document.querySelector('#avatar-sign-in');
  if (!botao) return null;
  const partes = (botao.innerText || '').split('\n').map((p) => p.trim()).filter((p) => p.length > 1);
  return { nome: partes[0] || '', perfil: partes[1] || '' };
}

async function paginaLerLista(maxPaginas) {
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
  const achar = () => Array.from(document.querySelectorAll('table')).find((t) => {
    const cab = Array.from(t.querySelectorAll('th')).map((h) => h.innerText.trim().toLowerCase());
    return cab.includes('prazo') && cab.some((c) => c.startsWith('n') && c.includes('mero'));
  });
  const total = () => {
    const m = (document.body.innerText.match(/Total de registros:\s*(\d+)/) || [])[1];
    return m ? parseInt(m, 10) : null;
  };
  const primeira = () => {
    const t = achar();
    const td = t && t.querySelector('tbody tr td');
    return td ? td.innerText.trim() : '';
  };
  const ler = () => {
    const t = achar();
    if (!t) return null;
    const cab = Array.from(t.querySelectorAll('th')).map((h) => h.innerText.trim());
    const linhas = Array.from(t.querySelectorAll('tbody tr')).map((tr) =>
      Array.from(tr.querySelectorAll('td')).map((td) => {
        const a = td.querySelector('a');
        return { texto: (td.innerText || '').trim(), href: a ? a.href : '' };
      })).filter((l) => l.length);
    return { cab, linhas, total: total() };
  };

  // Espera a tabela ter linhas. "Total de registros: 0" só vale depois de alguns segundos.
  const inicio = Date.now();
  let pronto = false;
  while (Date.now() - inicio < 30000) {
    const t = achar();
    if (t) {
      const linhas = Array.from(t.querySelectorAll('tbody tr')).filter((tr) => tr.querySelectorAll('td').length > 3).length;
      if (linhas > 0) { pronto = true; break; }
      if (total() === 0 && Date.now() - inicio > 6000) { pronto = true; break; }
    }
    await esperar(400);
  }
  if (!pronto) return { erro: 'O Fala.BR demorou para devolver a lista.' };

  const primeiraLeitura = ler();
  if (!primeiraLeitura) return { erro: 'A tabela de manifestações não apareceu.' };
  const cab = primeiraLeitura.cab;
  let linhas = primeiraLeitura.linhas;
  let passos = 0;
  while (passos < maxPaginas) {
    const botao = document.querySelector('[id$="pagination-arrows-right-btn"]');
    if (!botao || botao.disabled || botao.getAttribute('aria-disabled') === 'true') break;
    const marca = primeira();
    botao.click();
    passos += 1;
    let trocou = false;
    const t0 = Date.now();
    while (Date.now() - t0 < 10000) {
      const agora = primeira();
      if (agora && agora !== marca) { trocou = true; break; }
      await esperar(300);
    }
    if (!trocou) break;
    const lida = ler();
    if (lida) linhas = linhas.concat(lida.linhas);
  }
  return { cab, linhas, total: primeiraLeitura.total };
}

function paginaEsperarBotao(seletor) {
  const el = document.querySelector(seletor);
  return !!el && !el.disabled && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
}

function paginaClicar(seletor) {
  const el = document.querySelector(seletor);
  if (!el) return false;
  el.click();
  return true;
}

function paginaDesmarcarDados() {
  const caixa = document.querySelector('#chkExibeDadosManifestante');
  if (caixa && caixa.checked) caixa.click(); // "Incluir dados do manifestante": fica desmarcado
  return !!caixa;
}

function paginaAnexos() {
  const t = document.querySelector('#idAnexosTable') || document.querySelector('[id^=idAnexosTable]');
  const caixa = t ? (t.closest('section, .br-table, div') || t) : null;
  const m = caixa ? (caixa.innerText.match(/Total de registros:\s*(\d+)/) || [])[1] : null;
  const linhas = t ? Array.from(t.querySelectorAll('tbody tr')).filter((tr) => tr.querySelectorAll('td').length > 1).length : 0;
  const botao = document.querySelector('#idBaixarTodosAnexos');
  return {
    total: m ? parseInt(m, 10) : null,
    linhas,
    botao: !!botao && !botao.disabled && !!(botao.offsetWidth || botao.offsetHeight),
  };
}

// Roda no mundo da página (MAIN) para ver os arquivos que o próprio Fala.BR gera ao exportar.
function paginaInstalarCaptura() {
  if (window.__laiCaptura) return 'ja';
  const L = (window.__laiCaptura = { itens: [], log: [], urls: {} });
  const nota = (t) => { if (L.log.length < 80) L.log.push(String(t).slice(0, 200)); };
  const eArquivo = (tipo, cd) =>
    /pdf|zip|octet-stream|msword|officedocument|ms-excel|rtf/i.test(tipo || '') || /attachment/i.test(cd || '');
  const nomeDoCabecalho = (cd) => {
    const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd || '');
    if (!m) return '';
    try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; }
  };
  const guardar = (blob, origem, nome) => {
    const item = { blob, origem, nome: nome || '', tipo: blob.type || '' };
    L.itens.push(item);
    nota('capturado ' + origem + ' ' + (blob.type || '?') + ' ' + blob.size);
    return item;
  };

  const buscar = window.fetch;
  window.fetch = function () {
    const promessa = buscar.apply(this, arguments);
    promessa.then((r) => {
      try {
        const tipo = r.headers.get('content-type') || '';
        const cd = r.headers.get('content-disposition') || '';
        nota('fetch ' + r.status + ' ' + tipo.slice(0, 40));
        if (r.ok && eArquivo(tipo, cd)) r.clone().blob().then((b) => guardar(b, 'fetch', nomeDoCabecalho(cd)));
      } catch (e) { /* ignora */ }
    }).catch(() => {});
    return promessa;
  };

  const enviar = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener('load', () => {
      try {
        const tipo = this.getResponseHeader('content-type') || '';
        const cd = this.getResponseHeader('content-disposition') || '';
        nota('xhr ' + this.status + ' ' + tipo.slice(0, 40));
        if (this.status >= 200 && this.status < 300 && eArquivo(tipo, cd)) {
          if (this.response instanceof Blob) guardar(this.response, 'xhr', nomeDoCabecalho(cd));
          else if (this.response instanceof ArrayBuffer) guardar(new Blob([this.response], { type: tipo }), 'xhr', nomeDoCabecalho(cd));
        }
      } catch (e) { /* ignora */ }
    });
    return enviar.apply(this, arguments);
  };

  const criarUrl = URL.createObjectURL;
  URL.createObjectURL = function (obj) {
    const url = criarUrl.apply(this, arguments);
    if (obj instanceof Blob && obj.size > 0) L.urls[url] = guardar(obj, 'blob-url', '');
    return url;
  };

  const ehDownload = (a) => {
    try { return !!a && a.tagName === 'A' && (a.hasAttribute('download') || /^blob:/.test(a.href)); } catch (e) { return false; }
  };
  const tratar = (a) => {
    const item = L.urls[a.href];
    if (item) { if (a.download) item.nome = a.download; return; }
    if (/^https?:/.test(a.href)) {
      buscar(a.href, { credentials: 'include' }).then((r) => (r.ok ? r.blob() : null))
        .then((b) => { if (b && b.size) guardar(b, 'link', a.download || ''); }).catch(() => {});
    }
  };
  const cliqueOriginal = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (ehDownload(this)) { nota('link de download interceptado'); tratar(this); return undefined; }
    return cliqueOriginal.apply(this, arguments);
  };
  document.addEventListener('click', (ev) => {
    const a = ev.target && ev.target.closest ? ev.target.closest('a') : null;
    if (ehDownload(a)) { ev.preventDefault(); nota('clique em link de download interceptado'); tratar(a); }
  }, true);
  return 'instalada';
}

async function paginaListarCapturas() {
  const L = window.__laiCaptura;
  if (!L) return { itens: [], log: ['captura não instalada'] };
  const itens = [];
  for (let i = 0; i < L.itens.length; i++) {
    const it = L.itens[i];
    const cabeca = Array.from(new Uint8Array(await it.blob.slice(0, 16).arrayBuffer()));
    itens.push({ i, tamanho: it.blob.size, tipo: it.tipo, nome: it.nome, origem: it.origem, cabeca });
  }
  return { itens, log: L.log.slice() };
}

function paginaLerCaptura(i, inicio, fim) {
  const L = window.__laiCaptura;
  const blob = L.itens[i].blob.slice(inicio, fim);
  return new Promise((resolve) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(String(leitor.result).split(',')[1] || '');
    leitor.readAsDataURL(blob);
  });
}

// ------------------------------------------------------------ utilidades da aba

async function executar(abaId, func, args, mundo) {
  const [resultado] = await chrome.scripting.executeScript({
    target: { tabId: abaId }, func, args: args || [], world: mundo || 'ISOLATED',
  });
  return resultado ? resultado.result : undefined;
}

async function aguardarCarga(abaId, limite) {
  await dormir(600);
  const fim = Date.now() + (limite || 45000);
  while (Date.now() < fim) {
    const aba = await chrome.tabs.get(abaId);
    if (aba.status === 'complete') {
      if (!/^https:\/\/falabr\.cgu\.gov\.br\//.test(aba.url || '')) {
        throw new Error('O login no Fala.BR expirou. Entre de novo com o gov.br e tente outra vez.');
      }
      return;
    }
    await dormir(300);
  }
  throw new Error('A página do Fala.BR demorou para carregar.');
}

async function abrirAba(url) {
  const aba = await chrome.tabs.create({ url, active: false });
  return aba.id;
}

async function fecharAba(abaId) {
  try { await chrome.tabs.remove(abaId); } catch (e) { /* já fechada */ }
}

async function esperarPor(abaId, func, args, limite) {
  const fim = Date.now() + limite;
  while (Date.now() < fim) {
    if (job && job.cancelar) throw new Error('Cancelado.');
    try {
      if (await executar(abaId, func, args)) return true;
    } catch (e) { /* a página ainda está carregando */ }
    await dormir(400);
  }
  return false;
}

// ------------------------------------------------------------ status

async function status() {
  const abas = await chrome.tabs.query({ url: FALABR + '/*' });
  let usuario = null;
  for (const aba of abas) {
    try {
      const usuarioDaAba = await executar(aba.id, paginaLerUsuario);
      if (usuarioDaAba && usuarioDaAba.nome) { usuario = usuarioDaAba; break; }
    } catch (e) { /* aba carregando ou sem acesso */ }
  }
  return {
    instalada: true, versao: CFG.versao, servidor: CFG.servidor,
    abaFalabr: abas.length > 0, online: !!usuario,
    nome: usuario ? usuario.nome : '', perfil: usuario ? usuario.perfil : '',
    ocupada: !!job,
  };
}

// ------------------------------------------------------------ trazer NUPs

function baseDaUrl(url) {
  try {
    const u = new URL(url);
    if (u.hostname !== 'falabr.cgu.gov.br' || !u.pathname.includes('manifestacao/tratar')) return null;
    const base = { tipoFormulario: u.searchParams.get('tipoFormulario') || '3' };
    if (u.searchParams.get('ouvidoriaDestino')) base.ouvidoriaDestino = u.searchParams.get('ouvidoriaDestino');
    return base;
  } catch (e) { return null; }
}

async function descobrirBase(guardada) {
  const abas = await chrome.tabs.query({ url: FALABR + '/*' });
  for (const aba of abas) {
    const base = baseDaUrl(aba.url);
    if (base && base.ouvidoriaDestino) return base;
  }
  if (guardada && guardada.ouvidoriaDestino) return guardada;
  throw new Error('Só na primeira vez: no Fala.BR, abra Tratar manifestações e deixe a lista na tela. ' +
    'Depois clique em Trazer NUPs de novo. O sistema guarda o órgão e não pede isso outra vez.');
}

async function tarefaTrazer(dados) {
  const base = await descobrirBase(dados && dados.base);
  const grupos = {};
  let n = 0;
  for (const [nome, situacoes] of GRUPOS) {
    n += 1;
    await progresso({ etapa: 'Lendo os pedidos ' + (nome === 'abertas' ? 'abertos' : 'encerrados') + ' (' + n + ' de ' + GRUPOS.length + ')' });
    const params = new URLSearchParams({ tipoFormulario: base.tipoFormulario, ouvidoriaDestino: base.ouvidoriaDestino, situacoes });
    const abaId = await abrirAba(FALABR + '/web/manifestacao/tratar?' + params.toString().replace(/%2C/g, ','));
    try {
      await aguardarCarga(abaId);
      const lido = await executar(abaId, paginaLerLista, [MAX_PAGINAS]);
      if (!lido || lido.erro) throw new Error((lido && lido.erro) || 'Não consegui ler a lista do Fala.BR.');
      grupos[nome] = lido;
    } finally {
      await fecharAba(abaId);
    }
    if (job.cancelar) throw new Error('Cancelado.');
  }
  await progresso({ etapa: 'Gravando no sistema' });
  await api('leitura/', { base, grupos });
}

// ------------------------------------------------------------ automatizar pastas

const ehPdf = (c) => c.cabeca && c.cabeca[0] === 37 && c.cabeca[1] === 80 && c.cabeca[2] === 68 && c.cabeca[3] === 70;
const assinatura = (c) => c.tamanho + ':' + (c.cabeca || []).join(',');

async function capturasDaPagina(abaId) {
  let lista;
  try { lista = await executar(abaId, paginaListarCapturas, [], 'MAIN'); } catch (e) { lista = { itens: [], log: [] }; }
  const unicos = [];
  const vistos = new Set();
  for (const c of lista.itens) {
    const chave = assinatura(c);
    if (vistos.has(chave)) continue;
    vistos.add(chave);
    unicos.push(Object.assign({ origem: 'pagina' }, c, { fonte: c.origem }));
  }
  const baixados = job.baixados.map((b, i) => ({
    origem: 'download', i, tamanho: b.blob.size, tipo: b.tipo, nome: b.nome, cabeca: b.cabeca, fonte: 'download',
  }));
  return { itens: unicos.concat(baixados), log: lista.log };
}

async function aguardarArquivo(abaId, aceita, ignorar, limite) {
  const fim = Date.now() + limite;
  while (Date.now() < fim) {
    if (job.cancelar) throw new Error('Cancelado.');
    const { itens } = await capturasDaPagina(abaId);
    const achado = itens.find((c) => !ignorar.has(assinatura(c)) && aceita(c));
    if (achado) {
      await dormir(1200); // dá tempo de chegarem os outros arquivos do mesmo clique
      const todos = (await capturasDaPagina(abaId)).itens.filter((c) => !ignorar.has(assinatura(c)));
      return todos;
    }
    await dormir(700);
  }
  return null;
}

async function obterBlob(abaId, captura) {
  if (captura.origem === 'download') return job.baixados[captura.i].blob;
  const partes = [];
  for (let inicio = 0; inicio < captura.tamanho; inicio += PEDACO) {
    const b64 = await executar(abaId, paginaLerCaptura, [captura.i, inicio, Math.min(inicio + PEDACO, captura.tamanho)], 'MAIN');
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let k = 0; k < bin.length; k++) bytes[k] = bin.charCodeAt(k);
    partes.push(bytes);
  }
  return new Blob(partes, { type: captura.tipo || 'application/octet-stream' });
}

async function diagnostico(abaId) {
  try {
    const { itens, log } = await capturasDaPagina(abaId);
    return 'Capturas: ' + itens.map((c) => c.fonte + ' ' + (c.tipo || '?') + ' ' + c.tamanho).join('; ') +
      ' | Rede da página: ' + log.slice(-8).join('; ') + ' | Downloads: ' + job.diag.slice(-4).join('; ');
  } catch (e) { return ''; }
}

async function baixarPedido(item, posicao) {
  const abaId = await abrirAba(item.link);
  job.baixados = [];
  job.diag = [];
  job.esperaDownload = false;
  try {
    await progresso({ nup: item.nup, atual: posicao, etapa: 'Abrindo o pedido' });
    await aguardarCarga(abaId);
    await executar(abaId, paginaInstalarCaptura, [], 'MAIN');
    if (!(await esperarPor(abaId, paginaEsperarBotao, ['#btnExportar'], 30000))) {
      throw new Error('O botão Exportar não apareceu. Confira se o login no Fala.BR continua ativo.');
    }
    await dormir(1500); // a tabela de anexos carrega depois dos botões

    await progresso({ etapa: 'Exportando o PDF' });
    job.esperaDownload = true;
    await executar(abaId, paginaClicar, ['#btnExportar']);
    if (!(await esperarPor(abaId, paginaEsperarBotao, [MODAL + '-button-primary'], 20000))) {
      throw new Error('A confirmação do Exportar não apareceu.');
    }
    await executar(abaId, paginaDesmarcarDados);
    await dormir(300);
    await executar(abaId, paginaClicar, [MODAL + '-button-primary']);
    const arquivosPdf = await aguardarArquivo(abaId, ehPdf, new Set(), 90000);
    if (!arquivosPdf) throw new Error('O Exportar não devolveu um PDF. ' + (await diagnostico(abaId)));
    const pdf = arquivosPdf.find(ehPdf);
    const pdfBlob = await obterBlob(abaId, pdf);

    const anexos = [];
    const info = await executar(abaId, paginaAnexos);
    if (((info.total || info.linhas || 0) > 0) && info.botao) {
      await progresso({ etapa: 'Baixando os anexos' });
      const ignorar = new Set((await capturasDaPagina(abaId)).itens.map(assinatura));
      await executar(abaId, paginaClicar, ['#idBaixarTodosAnexos']);
      const arquivos = await aguardarArquivo(abaId, () => true, ignorar, 120000);
      if (!arquivos) throw new Error('Os anexos não baixaram. ' + (await diagnostico(abaId)));
      for (const c of arquivos) anexos.push({ nome: c.nome, blob: await obterBlob(abaId, c) });
    }
    job.esperaDownload = false;

    await progresso({ etapa: 'Enviando para o sistema' });
    const formulario = new FormData();
    formulario.append('nup', item.nup);
    formulario.append('pdf', pdfBlob, 'DetalhesNUP.pdf');
    anexos.forEach((a, i) => formulario.append('anexo', a.blob, a.nome || ('anexo-' + (i + 1))));
    await api('pedido/', null, formulario);
  } finally {
    job.esperaDownload = false;
    await fecharAba(abaId);
  }
}

async function tarefaPastas(dados) {
  const itens = (dados && dados.itens) || [];
  let posicao = (dados && dados.jaProntos) || 0;
  for (const item of itens) {
    if (job.cancelar) break;
    posicao += 1;
    try {
      await baixarPedido(item, posicao);
    } catch (e) {
      if (job.cancelar) break;
      await api('falha/', { nup: item.nup, erro: String(e.message || e).slice(0, 600) });
    }
  }
  await api('concluir/', {});
}

chrome.downloads.onCreated.addListener(async (baixa) => {
  if (!job || !job.esperaDownload) return;
  const url = baixa.finalUrl || baixa.url || '';
  job.diag.push('download ' + url.slice(0, 100));
  try { await chrome.downloads.cancel(baixa.id); await chrome.downloads.erase({ id: baixa.id }); } catch (e) { /* já cancelado */ }
  if (!/^https?:/.test(url)) return;
  try {
    const r = await fetch(url, { credentials: 'include' });
    if (!r.ok) { job.diag.push('download recusado ' + r.status); return; }
    const blob = await r.blob();
    const cabeca = Array.from(new Uint8Array(await blob.slice(0, 16).arrayBuffer()));
    const nome = (baixa.filename || '').split(/[\\/]/).pop();
    job.baixados.push({ blob, tipo: blob.type, nome, cabeca });
  } catch (e) { job.diag.push('download falhou'); }
});

// ------------------------------------------------------------ mensagens da página do sistema e do popup

async function iniciarTarefa(tipo, dados) {
  if (job) return { ok: false, erro: 'A extensão já está executando uma tarefa. Aguarde o fim.' };
  job = { tipo, cancelar: false, esperaDownload: false, baixados: [], diag: [] };
  const batimento = setInterval(() => {
    chrome.runtime.getPlatformInfo(() => {}); // mantém o serviço da extensão acordado
    progresso({}).catch(() => {});
  }, 10000);
  (async () => {
    try {
      if (tipo === 'trazer') await tarefaTrazer(dados);
      else await tarefaPastas(dados);
    } catch (e) {
      try { await progresso({ erro: String(e.message || e).slice(0, 600), fim: true }); } catch (e2) { /* sem rede */ }
    } finally {
      clearInterval(batimento);
      job = null;
    }
  })();
  return { ok: true };
}

chrome.runtime.onMessage.addListener((msg, remetente, responder) => {
  (async () => {
    const deConteudo = remetente.tab && (remetente.tab.url || '').indexOf(CFG.servidor + '/lai/') === 0;
    const dePopup = !remetente.tab && remetente.id === chrome.runtime.id;
    if (!deConteudo && !dePopup) { responder({ ok: false, erro: 'Origem não permitida.' }); return; }
    try {
      if (msg.tipo === 'status') responder(await status());
      else if (msg.tipo === 'trazer' || msg.tipo === 'pastas') responder(await iniciarTarefa(msg.tipo, msg.dados));
      else if (msg.tipo === 'cancelar') { if (job) job.cancelar = true; responder({ ok: true }); }
      else responder({ ok: false, erro: 'Mensagem desconhecida.' });
    } catch (e) {
      responder({ ok: false, erro: String(e.message || e) });
    }
  })();
  return true;
});
