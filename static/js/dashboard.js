/* Dashboard da Gestão — animações com Motion e gráfico de entradas × saídas.
 *
 * Sem Motion (ou com "reduzir movimento" ligado) tudo continua funcionando,
 * só que sem animar. O período troca por fetch: a página não recarrega e o
 * gráfico anima de novo com os números novos. */
(function () {
    'use strict';

    var raiz = document.getElementById('dash');
    if (!raiz) return;

    var M = window.Motion || {};
    var reduzido = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var animar = typeof M.animate === 'function' && !reduzido;
    if (!animar) document.documentElement.classList.remove('dash-anim');

    var SVG = 'http://www.w3.org/2000/svg';
    var form = document.getElementById('dash-form');
    var visivel = { entradas: true, saidas: true, acervo: true };
    var pedido = 0;

    /* ------------------------------------------------------------------ */
    /* Utilidades                                                          */
    /* ------------------------------------------------------------------ */
    function qs(sel, ctx) { return (ctx || document).querySelector(sel); }
    function qsa(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
    function fmt(n) { return Number(n).toLocaleString('pt-BR'); }

    function el(nome, attrs, pai) {
        var no = document.createElementNS(SVG, nome);
        for (var k in attrs) if (Object.prototype.hasOwnProperty.call(attrs, k)) no.setAttribute(k, attrs[k]);
        if (pai) pai.appendChild(no);
        return no;
    }

    function quandoVisivel(elemento, fn) {
        if (typeof M.inView === 'function') {
            M.inView(elemento, function () { fn(); }, { margin: '0px 0px -4% 0px' });
        } else {
            fn();
        }
    }

    function formatarContagem(no, valor) {
        var texto = fmt(Math.round(valor));
        if (no.getAttribute('data-sinal') && valor > 0) texto = '+' + texto;
        no.textContent = texto;
    }

    /* ------------------------------------------------------------------ */
    /* Entradas animadas                                                   */
    /* ------------------------------------------------------------------ */
    function entrar(elemento, atraso) {
        if (!animar) return;
        animate(elemento, {
            opacity: [0, 1],
            transform: ['translateY(18px)', 'translateY(0px)']
        }, { duration: 0.55, delay: atraso || 0, ease: [0.22, 1, 0.36, 1] }).then(function () {
            // transform fixo deixaria o bloco como "âncora" de filhos fixed (painéis no celular).
            elemento.style.transform = '';
        });
    }

    function contar(no, atraso) {
        var alvo = parseInt(no.getAttribute('data-count'), 10) || 0;
        if (!animar || !alvo) { formatarContagem(no, alvo); return; }
        animate(0, alvo, {
            duration: Math.min(1.4, 0.6 + Math.log10(Math.abs(alvo) + 1) * 0.28),
            delay: atraso || 0,
            ease: 'easeOut',
            onUpdate: function (v) { formatarContagem(no, v); },
            onComplete: function () { formatarContagem(no, alvo); }
        });
    }

    function animate() { return M.animate.apply(M, arguments); }

    function preparar(escopo) {
        if (!animar) return;
        qsa('[data-count]', escopo).forEach(function (no) { formatarContagem(no, 0); });
        qsa('[data-scroll-bars] .grafico__barra', escopo).forEach(function (b) {
            b.style.transformOrigin = 'left center';
            b.style.transform = 'scaleX(0)';
        });
    }

    function iniciarEscopo(escopo, primeira) {
        var blocos = qsa('[data-anim]', escopo);
        if (escopo.hasAttribute && escopo.hasAttribute('data-anim')) blocos.unshift(escopo);
        blocos.forEach(function (bloco, i) {
            var atraso = primeira ? Math.min(i, 10) * 0.05 : Math.min(i, 3) * 0.07;
            if (!animar) return;
            quandoVisivel(bloco, function () { entrar(bloco, atraso); });
        });

        qsa('[data-count]', escopo).forEach(function (no, i) {
            if (!animar) return;
            quandoVisivel(no, function () { contar(no, 0.12 + Math.min(i, 8) * 0.03); });
        });

        qsa('[data-scroll-bars]', escopo).forEach(function (secao) {
            var barras = qsa('.grafico__barra', secao);
            if (!animar || !barras.length) return;
            quandoVisivel(secao, function () {
                animate(barras, { transform: ['scaleX(0)', 'scaleX(1)'] }, {
                    duration: 0.7, ease: [0.22, 1, 0.36, 1],
                    delay: M.stagger ? M.stagger(0.06, { startDelay: 0.15 }) : 0
                });
            });
        });
    }

    function levitar() {
        if (!animar || typeof M.hover !== 'function') return;
        M.hover('[data-hover-lift]', function (alvo) {
            animate(alvo, { transform: 'translateY(-4px)' }, { duration: 0.18, ease: 'easeOut' });
            return function () {
                animate(alvo, { transform: 'translateY(0px)' }, { duration: 0.22, ease: 'easeOut' });
            };
        });
    }

    function flutuar() {
        if (!animar) return;
        var a = qs('.dash-hero__blob--a');
        var b = qs('.dash-hero__blob--b');
        if (a) animate(a, { transform: ['translate(0px,0px)', 'translate(-60px,40px)', 'translate(0px,0px)'] },
            { duration: 16, repeat: Infinity, ease: 'easeInOut' });
        if (b) animate(b, { transform: ['translate(0px,0px)', 'translate(70px,-30px)', 'translate(0px,0px)'] },
            { duration: 20, repeat: Infinity, ease: 'easeInOut' });
    }

    /* ------------------------------------------------------------------ */
    /* Seletor Dia / Semana / Mês / Ano                                    */
    /* ------------------------------------------------------------------ */
    function posicionarMarca(imediato) {
        var marca = qs('.dash-seg__marca');
        var marcado = qs('.dash-seg__opcao input:checked');
        if (!marca || !marcado) return;
        var opcao = marcado.parentElement;
        var x = opcao.offsetLeft, w = opcao.offsetWidth;
        if (!w) return;
        if (!animar) {
            marca.style.width = w + 'px';
            marca.style.transform = 'translateX(' + x + 'px)';
        } else if (imediato) {
            animate(marca, { x: x, width: w }, { duration: 0 });
        } else {
            animate(marca, { x: x, width: w }, { type: 'spring', visualDuration: 0.4, bounce: 0.2 });
        }
    }

    /* ------------------------------------------------------------------ */
    /* Popovers                                                            */
    /* ------------------------------------------------------------------ */
    function abrirPop(pop) {
        var painel = qs('[data-pop-painel]', pop);
        var botao = qs('[data-pop-botao]', pop);
        if (!painel.hidden) return;
        fecharPops(pop);
        painel.hidden = false;
        botao.setAttribute('aria-expanded', 'true');
        if (animar) {
            animate(painel, {
                opacity: [0, 1],
                transform: ['scale(0.96) translateY(-8px)', 'scale(1) translateY(0px)']
            }, { duration: 0.2, ease: [0.22, 1, 0.36, 1] });
        }
        var primeiro = qs('input, select', painel);
        if (primeiro && window.innerWidth > 720) primeiro.focus({ preventScroll: true });
    }

    function fecharPop(pop) {
        var painel = qs('[data-pop-painel]', pop);
        var botao = qs('[data-pop-botao]', pop);
        if (painel.hidden) return;
        botao.setAttribute('aria-expanded', 'false');
        if (!animar) { painel.hidden = true; return; }
        animate(painel, { opacity: [1, 0], transform: ['scale(1)', 'scale(0.97)'] },
            { duration: 0.14, ease: 'easeIn' }).then(function () { painel.hidden = true; });
    }

    function fecharPops(exceto) {
        qsa('[data-pop]').forEach(function (pop) { if (pop !== exceto) fecharPop(pop); });
    }

    function iniciarPops() {
        qsa('[data-pop]').forEach(function (pop) {
            qs('[data-pop-botao]', pop).addEventListener('click', function (ev) {
                ev.stopPropagation();
                if (qs('[data-pop-painel]', pop).hidden) abrirPop(pop); else fecharPop(pop);
            });
            qs('[data-pop-painel]', pop).addEventListener('click', function (ev) { ev.stopPropagation(); });
        });
        document.addEventListener('click', function () { fecharPops(); });
        document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') fecharPops(); });
    }

    /* ------------------------------------------------------------------ */
    /* Troca do período sem recarregar a página                            */
    /* ------------------------------------------------------------------ */
    function iso(d) {
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var dia = String(d.getDate()).padStart(2, '0');
        return d.getFullYear() + '-' + m + '-' + dia;
    }

    function intervaloRapido(tipo) {
        var hoje = new Date();
        var ano = hoje.getFullYear(), mes = hoje.getMonth();
        if (tipo === 'mes') return [new Date(ano, mes, 1), hoje];
        if (tipo === 'mes-anterior') return [new Date(ano, mes - 1, 1), new Date(ano, mes, 0)];
        if (tipo === 'ano') return [new Date(ano, 0, 1), hoje];
        return [new Date(ano - 1, 0, 1), new Date(ano - 1, 11, 31)];
    }

    // Setas de "dia anterior / próximo dia": só aparecem quando a tela mostra um dia.
    function sincronizarSetas() {
        var modoDia = !!form.getAttribute('data-modo-dia');
        var dia = form.getAttribute('data-dia');
        var hoje = form.getAttribute('data-hoje');
        qsa('[data-dia-nav]', form).forEach(function (botao) {
            botao.hidden = !modoDia;
            if (botao.getAttribute('data-dia-nav') === '1') botao.disabled = !dia || dia >= hoje;
        });
    }

    function deslocarDia(passo) {
        var partes = (form.getAttribute('data-dia') || '').split('-');
        if (partes.length !== 3) return;
        var data = new Date(Number(partes[0]), Number(partes[1]) - 1, Number(partes[2]) + passo);
        if (iso(data) > form.getAttribute('data-hoje')) return;
        form.elements.inicio.value = iso(data);
        form.elements.fim.value = '';
        carregar();
    }

    function urlAtual() {
        var dados = new FormData(form);
        var params = new URLSearchParams();
        dados.forEach(function (valor, chave) { if (String(valor).trim() !== '') params.append(chave, valor); });
        var texto = params.toString();
        return window.location.pathname + (texto ? '?' + texto : '');
    }

    function carregar() {
        var minha = ++pedido;
        var url = urlAtual();
        var regioes = qsa('[data-dash-live]');
        regioes.forEach(function (r) { r.classList.add('dash-carregando'); });

        fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
            .then(function (resp) {
                if (!resp.ok) throw new Error('http ' + resp.status);
                return resp.text();
            })
            .then(function (html) {
                if (minha !== pedido) return;
                var doc = new DOMParser().parseFromString(html, 'text/html');
                var novoForm = doc.getElementById('dash-form');
                if (!novoForm) throw new Error('resposta inesperada');

                qsa('[data-pop-botao]', form).forEach(function (botao, i) {
                    var novo = qsa('[data-pop-botao]', novoForm)[i];
                    if (novo) botao.innerHTML = novo.innerHTML;
                });
                ['data-modo-dia', 'data-dia', 'data-hoje'].forEach(function (atributo) {
                    form.setAttribute(atributo, novoForm.getAttribute(atributo) || '');
                });
                sincronizarSetas();
                var marcado = qs('input[name="unidade"]:checked', novoForm);
                if (marcado) {
                    var atual = qs('input[name="unidade"][value="' + marcado.value + '"]', form);
                    if (atual) atual.checked = true;
                    posicionarMarca(false);
                }

                regioes.forEach(function (regiao) {
                    var novaRegiao = doc.getElementById(regiao.id);
                    if (!novaRegiao) return;
                    regiao.innerHTML = novaRegiao.innerHTML;
                    regiao.classList.remove('dash-carregando');
                    preparar(regiao);
                    iniciarEscopo(regiao, false);
                });
                iniciarGrafico(true);
                window.history.replaceState(null, '', url);
            })
            .catch(function () { form.submit(); });
    }

    function iniciarControles() {
        iniciarPops();
        posicionarMarca(true);
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { posicionarMarca(true); });
        window.addEventListener('resize', function () { posicionarMarca(true); });

        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            fecharPops();
            carregar();
        });

        qsa('input[name="unidade"]', form).forEach(function (radio) {
            radio.addEventListener('change', function () {
                form.elements.inicio.value = '';
                form.elements.fim.value = '';
                posicionarMarca(false);
                fecharPops();
                carregar();
            });
        });

        qsa('[data-dia-nav]', form).forEach(function (botao) {
            botao.addEventListener('click', function () {
                deslocarDia(Number(botao.getAttribute('data-dia-nav')));
            });
        });
        sincronizarSetas();

        qsa('[data-rapido]', form).forEach(function (botao) {
            botao.addEventListener('click', function () {
                var faixa = intervaloRapido(botao.getAttribute('data-rapido'));
                form.elements.inicio.value = iso(faixa[0]);
                form.elements.fim.value = iso(faixa[1]);
                fecharPops();
                carregar();
            });
        });

        qs('[data-limpar-periodo]', form).addEventListener('click', function () {
            form.elements.inicio.value = '';
            form.elements.fim.value = '';
            fecharPops();
            carregar();
        });

        qs('[data-limpar-filtros]', form).addEventListener('click', function () {
            ['grupo', 'analista', 'secretaria', 'especie'].forEach(function (nome) {
                form.elements[nome].value = '';
            });
            fecharPops();
            carregar();
        });

        // Legenda: ligar/desligar séries (delegação: o cartão é trocado a cada período).
        document.addEventListener('click', function (ev) {
            var botao = ev.target.closest && ev.target.closest('.dash-legenda__item');
            if (!botao) return;
            var serie = botao.getAttribute('data-serie');
            visivel[serie] = !visivel[serie];
            sincronizarLegenda();
            qsa('#dash-grafico [data-grupo="' + serie + '"]').forEach(function (grupo) {
                grupo.style.pointerEvents = visivel[serie] ? '' : 'none';
                if (animar) animate(grupo, { opacity: visivel[serie] ? 1 : 0 }, { duration: 0.25 });
                else grupo.style.opacity = visivel[serie] ? 1 : 0;
            });
        });
    }

    function sincronizarLegenda() {
        qsa('.dash-legenda__item').forEach(function (botao) {
            botao.setAttribute('aria-pressed', visivel[botao.getAttribute('data-serie')] ? 'true' : 'false');
        });
    }

    /* ------------------------------------------------------------------ */
    /* Gráfico de entradas × saídas                                        */
    /* ------------------------------------------------------------------ */
    function lerDados() {
        var no = document.getElementById('dash-fluxo-dados');
        if (!no) return null;
        try { return JSON.parse(no.textContent); } catch (e) { return null; }
    }

    function escalaBonita(max) {
        if (max <= 4) return { topo: 4, passo: 1 };
        var base = Math.pow(10, Math.floor(Math.log10(max / 4)));
        var multiplos = [1, 2, 2.5, 5, 10];
        for (var i = 0; i < multiplos.length; i++) {
            var passo = base * multiplos[i];
            if (max / passo <= 4) return { topo: passo * 4, passo: passo };
        }
        return { topo: max, passo: max / 4 };
    }

    function caminhoSuave(pontos) {
        if (pontos.length === 1) return 'M' + pontos[0][0] + ',' + pontos[0][1];
        var d = 'M' + pontos[0][0] + ',' + pontos[0][1];
        for (var i = 0; i < pontos.length - 1; i++) {
            var p0 = pontos[i - 1] || pontos[i], p1 = pontos[i], p2 = pontos[i + 1], p3 = pontos[i + 2] || p2;
            var c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6;
            var c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6;
            d += ' C' + c1x + ',' + c1y + ' ' + c2x + ',' + c2y + ' ' + p2[0] + ',' + p2[1];
        }
        return d;
    }

    // As cores vêm das variáveis do dashboard.css (claro e escuro).
    function gradiente(defs, id, corTopo, corBase, opTopo, opBase) {
        var g = el('linearGradient', { id: id, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
        var topo = el('stop', { offset: '0%', 'stop-opacity': opTopo }, g);
        var base = el('stop', { offset: '100%', 'stop-opacity': opBase }, g);
        topo.style.stopColor = 'var(' + corTopo + ')';
        base.style.stopColor = 'var(' + corBase + ')';
        // Opacidade também pode vir de variável CSS (valor "--nome").
        if (typeof opTopo === 'string') topo.style.stopOpacity = 'var(' + opTopo + ')';
        if (typeof opBase === 'string') base.style.stopOpacity = 'var(' + opBase + ')';
    }

    function insight(dados) {
        var no = document.getElementById('dash-insight');
        if (!no) return;
        var baldes = dados.baldes;
        if (dados.modo_dia) {
            var escolhido = baldes[baldes.length - 1];
            var anteriores = baldes.slice(0, -1);
            var mediaE = anteriores.reduce(function (s, b) { return s + b.entradas; }, 0) / Math.max(1, anteriores.length);
            var mediaS = anteriores.reduce(function (s, b) { return s + b.saidas; }, 0) / Math.max(1, anteriores.length);
            var f1 = function (v) { return v.toLocaleString('pt-BR', { maximumFractionDigits: 1 }); };
            no.innerHTML = 'Neste dia: <strong>' + fmt(escolhido.entradas) + '</strong> entraram e <strong>' +
                fmt(escolhido.saidas) + '</strong> saíram · Média dos ' + anteriores.length +
                ' dias anteriores: <strong>' + f1(mediaE) + '</strong> entradas e <strong>' + f1(mediaS) + '</strong> saídas por dia';
            return;
        }
        var maiorE = baldes[0], maiorS = baldes[0];
        baldes.forEach(function (b) {
            if (b.entradas > maiorE.entradas) maiorE = b;
            if (b.saidas > maiorS.saidas) maiorS = b;
        });
        var unidade = { dia: 'dia', semana: 'semana', mes: 'mês', ano: 'ano' }[dados.unidade];
        var media = (dados.totais.entradas / baldes.length).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
        var partes = [];
        if (maiorE.entradas > 0) partes.push('Mais entradas: <strong>' + fmt(maiorE.entradas) + '</strong> (' + maiorE.titulo + ')');
        if (maiorS.saidas > 0) partes.push('Mais saídas: <strong>' + fmt(maiorS.saidas) + '</strong> (' + maiorS.titulo + ')');
        partes.push('Média de <strong>' + media + '</strong> entradas por ' + unidade);
        no.innerHTML = partes.join(' · ');
    }

    function iniciarGrafico(forcarEntrada) {
        var caixa = document.getElementById('dash-grafico');
        var dados = lerDados();
        if (!caixa || !dados) return;
        sincronizarLegenda();
        insight(dados);
        desenhar(caixa, dados, forcarEntrada);
    }

    function desenhar(caixa, dados, comEntrada) {
        caixa.innerHTML = '';
        var baldes = dados.baldes;
        var n = baldes.length;
        var largura = Math.max(caixa.clientWidth, 320);
        var altura = largura < 560 ? 280 : 340;
        var m = { t: 16, r: 54, b: 34, l: 44 };
        var iw = largura - m.l - m.r, ih = altura - m.t - m.b;

        var maxBarra = 1;
        baldes.forEach(function (b) { maxBarra = Math.max(maxBarra, b.entradas, b.saidas); });
        var esc = escalaBonita(maxBarra);

        var amin = Infinity, amax = -Infinity;
        baldes.forEach(function (b) { amin = Math.min(amin, b.acervo); amax = Math.max(amax, b.acervo); });
        if (amax === amin) { amin -= 1; amax += 1; }
        var folga = (amax - amin) * 0.15;
        var alo = Math.max(0, Math.floor(amin - folga)), ahi = Math.ceil(amax + folga);
        if (ahi === alo) ahi = alo + 1;

        var yBarra = function (v) { return m.t + ih - (v / esc.topo) * ih; };
        var yAcervo = function (v) { return m.t + ih - ((v - alo) / (ahi - alo)) * ih; };
        var banda = iw / n;
        var xCentro = function (i) { return m.l + banda * i + banda / 2; };
        var larguraBarra = Math.max(3, Math.min(banda * 0.34, 24));
        var vao = Math.min(3, larguraBarra * 0.2);

        var svg = el('svg', { viewBox: '0 0 ' + largura + ' ' + altura, role: 'img', 'aria-label': 'Entraram, saíram e processos na CGM ao fim de cada intervalo' });
        svg.setAttribute('height', altura);
        var defs = el('defs', {}, svg);
        gradiente(defs, 'dash-grad-entrada', '--dash-entrada', '--dash-entrada-fim', 1, 1);
        gradiente(defs, 'dash-grad-saida', '--dash-saida', '--dash-saida-fim', 1, 1);
        gradiente(defs, 'dash-grad-acervo', '--dash-acervo-sombra', '--dash-acervo-sombra', '--dash-acervo-veu-topo', '--dash-acervo-veu-base');

        // Grade e eixos
        var grade = el('g', { 'class': 'grade' }, svg);
        var eixoY = el('g', {}, svg);
        var eixoA = el('g', { 'class': 'eixo-acervo' }, svg);
        for (var k = 0; k <= 4; k++) {
            var y = m.t + ih - (ih * k) / 4;
            el('line', { x1: m.l, x2: m.l + iw, y1: y, y2: y }, grade);
            var t = el('text', { x: m.l - 8, y: y + 4, 'text-anchor': 'end' }, eixoY);
            t.textContent = fmt(Math.round(esc.passo * k * 100) / 100);
            if (visivel.acervo) {
                var ta = el('text', { x: m.l + iw + 8, y: y + 4 }, eixoA);
                ta.textContent = fmt(Math.round(alo + ((ahi - alo) * k) / 4));
            }
        }

        // Rótulos do eixo X (pula alguns se estiver apertado)
        var eixoX = el('g', {}, svg);
        var passoRotulo = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 58))));
        baldes.forEach(function (b, i) {
            if (i % passoRotulo !== 0 && i !== n - 1) return;
            if (i !== n - 1 && n - 1 - i < passoRotulo / 2 && n > 2) return;
            var tx = el('text', { x: xCentro(i), y: altura - 10, 'text-anchor': 'middle' }, eixoX);
            tx.textContent = b.rotulo;
        });
        var indiceDestaque = -1;
        baldes.forEach(function (b, i) { if (dados.destaque && b.chave === dados.destaque) indiceDestaque = i; });
        if (indiceDestaque >= 0) {
            // O dia escolhido sempre tem rótulo e fica em negrito.
            var rotuloEscolhido = qsa('text', eixoX).filter(function (t) {
                return t.textContent === baldes[indiceDestaque].rotulo;
            })[0];
            if (!rotuloEscolhido) {
                rotuloEscolhido = el('text', { x: xCentro(indiceDestaque), y: altura - 10, 'text-anchor': 'middle' }, eixoX);
                rotuloEscolhido.textContent = baldes[indiceDestaque].rotulo;
            }
            rotuloEscolhido.setAttribute('class', 'rotulo-destaque');
        }

        // Faixas de destaque (hover)
        var faixas = el('g', {}, svg);
        if (indiceDestaque >= 0) {
            el('rect', {
                'class': 'faixa faixa--destaque', x: m.l + banda * indiceDestaque, y: m.t,
                width: banda, height: ih, rx: 6
            }, faixas);
        }
        var rects = baldes.map(function (b, i) {
            return el('rect', { 'class': 'faixa', x: m.l + banda * i, y: m.t, width: banda, height: ih, rx: 6 }, faixas);
        });

        // Área do acervo fica atrás das barras; a linha vem por cima delas.
        var pontos = baldes.map(function (b, i) { return [xCentro(i), yAcervo(b.acervo)]; });
        var area = null, linha = null, caminho = '';
        var grupoArea = el('g', { 'data-grupo': 'acervo' }, svg);
        if (n > 1) {
            caminho = caminhoSuave(pontos);
            area = el('path', { 'class': 'area-acervo', d: caminho + ' L' + pontos[n - 1][0] + ',' + (m.t + ih) + ' L' + pontos[0][0] + ',' + (m.t + ih) + ' Z' }, grupoArea);
        }

        // Barras
        var barrasE = el('g', { 'data-grupo': 'entradas' }, svg);
        var barrasS = el('g', { 'data-grupo': 'saidas' }, svg);
        var todasBarras = [];
        baldes.forEach(function (b, i) {
            var cx = xCentro(i);
            [[b.entradas, cx - larguraBarra - vao / 2, barrasE, 'entrada'],
             [b.saidas, cx + vao / 2, barrasS, 'saida']].forEach(function (cfg) {
                if (!cfg[0]) return;
                var h = Math.max(3, ih - (yBarra(cfg[0]) - m.t));
                var r = el('rect', {
                    'class': 'barra barra--' + cfg[3], x: cfg[1], y: m.t + ih - h,
                    width: larguraBarra, height: h, rx: Math.min(5, larguraBarra / 2)
                }, cfg[2]);
                if (indiceDestaque >= 0 && i !== indiceDestaque) r.style.opacity = 0.5;
                todasBarras.push(r);
            });
        });

        // Linha do acervo
        var grupoA = el('g', { 'data-grupo': 'acervo' }, svg);
        if (n > 1) {
            linha = el('path', { 'class': 'linha-acervo', d: caminho, pathLength: 1 }, grupoA);
        }
        var marcador = el('circle', { 'class': 'ponto-acervo', r: 0, cx: pontos[0][0], cy: pontos[0][1] }, grupoA);
        if (n === 1) marcador.setAttribute('r', 5);

        ['entradas', 'saidas', 'acervo'].forEach(function (serie) {
            qsa('[data-grupo="' + serie + '"]', svg).forEach(function (g) {
                if (!visivel[serie]) { g.style.opacity = 0; g.style.pointerEvents = 'none'; }
            });
        });

        caixa.appendChild(svg);

        // Dica flutuante
        var dica = document.createElement('div');
        dica.className = 'dash-dica';
        caixa.appendChild(dica);

        var atual = -1;
        function mostrar(i, clientX) {
            if (i === atual) return;
            if (atual >= 0) rects[atual].style.opacity = 0;
            atual = i;
            var b = baldes[i];
            rects[i].style.opacity = 0.07;
            var linhas = '<div class="dash-dica__titulo">' + b.titulo + '</div>';
            if (visivel.entradas) linhas += '<div class="dash-dica__linha"><span><i style="--cor:var(--dash-entrada)"></i>Entraram</span><b>' + fmt(b.entradas) + '</b></div>';
            if (visivel.saidas) linhas += '<div class="dash-dica__linha"><span><i style="--cor:var(--dash-saida)"></i>Saíram</span><b>' + fmt(b.saidas) + '</b></div>';
            if (visivel.entradas && visivel.saidas) linhas += '<div class="dash-dica__linha"><span>Saldo</span><b>' + (b.saldo > 0 ? '+' : '') + fmt(b.saldo) + '</b></div>';
            if (visivel.acervo) linhas += '<div class="dash-dica__linha"><span><i style="--cor:var(--dash-acervo)"></i>Na CGM ao fim</span><b>' + fmt(b.acervo) + '</b></div>';
            dica.innerHTML = linhas;

            var cx = xCentro(i);
            var w = dica.offsetWidth;
            var x = cx + 16;
            if (x + w > largura) x = cx - w - 16;
            x = Math.max(0, x);
            var y = m.t + 6;
            if (animar) {
                animate(dica, { x: x, y: y, opacity: 1 }, { type: 'spring', visualDuration: 0.25, bounce: 0.12 });
                animate(marcador, { cx: pontos[i][0], cy: pontos[i][1], r: visivel.acervo ? 5.5 : 0 }, { type: 'spring', visualDuration: 0.3, bounce: 0.2 });
            } else {
                dica.style.transform = 'translate(' + x + 'px,' + y + 'px)';
                dica.style.opacity = 1;
                marcador.setAttribute('cx', pontos[i][0]);
                marcador.setAttribute('cy', pontos[i][1]);
                marcador.setAttribute('r', visivel.acervo ? 5.5 : 0);
            }
        }

        function esconder() {
            if (atual >= 0) rects[atual].style.opacity = 0;
            atual = -1;
            if (animar) {
                animate(dica, { opacity: 0 }, { duration: 0.15 });
                if (n > 1) animate(marcador, { r: 0 }, { duration: 0.15 });
            } else {
                dica.style.opacity = 0;
                if (n > 1) marcador.setAttribute('r', 0);
            }
        }

        function indiceDe(ev) {
            var caixaSvg = svg.getBoundingClientRect();
            var escala = largura / caixaSvg.width;
            var x = (ev.clientX - caixaSvg.left) * escala - m.l;
            if (x < 0 || x > iw) return -1;
            return Math.min(n - 1, Math.floor(x / banda));
        }

        svg.addEventListener('pointermove', function (ev) {
            var i = indiceDe(ev);
            if (i < 0) esconder(); else mostrar(i);
        });
        svg.addEventListener('pointerleave', esconder);

        if (n === 0 || (!dados.totais.entradas && !dados.totais.saidas)) {
            var vazio = el('text', { 'class': 'vazio', x: largura / 2, y: m.t + ih / 2, 'text-anchor': 'middle' }, svg);
            vazio.textContent = 'Nenhum processo entrou ou saiu neste período.';
        }

        // Entrada animada
        if (animar && comEntrada !== false) {
            todasBarras.forEach(function (r) { r.style.transform = 'scaleY(0)'; });
            if (linha) { linha.style.strokeDasharray = 1; linha.style.strokeDashoffset = 1; }
            if (area) area.style.opacity = 0;

            quandoVisivel(caixa, function () {
                if (todasBarras.length) {
                    animate(todasBarras, { transform: ['scaleY(0)', 'scaleY(1)'] }, {
                        type: 'spring', visualDuration: 0.6, bounce: 0.18,
                        delay: M.stagger ? M.stagger(Math.min(0.03, 0.6 / n)) : 0
                    });
                }
                if (linha) {
                    animate(linha, { strokeDashoffset: [1, 0] }, { duration: 1.1, delay: 0.3, ease: 'easeInOut' });
                    animate(area, { opacity: [0, 1] }, { duration: 0.8, delay: 0.9 });
                }
            });
        }
    }

    /* ------------------------------------------------------------------ */
    /* Início                                                              */
    /* ------------------------------------------------------------------ */
    // Redesenha o gráfico quando a largura muda (janela ou menu lateral recolhido).
    var redimensionar;
    var larguraAnterior = raiz.clientWidth;
    function aoRedimensionar() {
        if (raiz.clientWidth === larguraAnterior) return;
        larguraAnterior = raiz.clientWidth;
        window.clearTimeout(redimensionar);
        redimensionar = window.setTimeout(function () { iniciarGrafico(false); posicionarMarca(true); }, 160);
    }
    if (typeof ResizeObserver === 'function') new ResizeObserver(aoRedimensionar).observe(raiz);
    else window.addEventListener('resize', aoRedimensionar);

    try {
        preparar(raiz);
        iniciarControles();
        iniciarEscopo(raiz, true);
        iniciarGrafico(true);
        levitar();
        flutuar();
    } catch (erro) {
        // Qualquer falha: mostra a página como está, sem esconder nada.
        document.documentElement.classList.remove('dash-anim');
        qsa('[data-count]').forEach(function (no) { formatarContagem(no, parseInt(no.getAttribute('data-count'), 10) || 0); });
        qsa('.grafico__barra').forEach(function (b) { b.style.transform = ''; });
        if (window.console) console.error('dashboard.js', erro);
    }
})();
