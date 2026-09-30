/* ==========================================================================
   Sistema de Protocolo - comportamentos compartilhados da interface.
   ========================================================================== */
(function () {
    'use strict';

    var DESKTOP = '(min-width: 1025px)';

    /* ---------------------------------------------------------------- Sidebar */
    function initSidebar() {
        var body = document.body;

        if (localStorage.getItem('sidebarCollapsed') === '1') {
            body.classList.add('sidebar-collapsed');
        }

        document.addEventListener('click', function (event) {
            if (event.target.closest('[data-sidebar-toggle]')) {
                if (window.matchMedia(DESKTOP).matches) {
                    var collapsed = body.classList.toggle('sidebar-collapsed');
                    localStorage.setItem('sidebarCollapsed', collapsed ? '1' : '0');
                } else {
                    body.classList.toggle('sidebar-open');
                }
                return;
            }
            if (event.target.closest('[data-sidebar-close]')) {
                body.classList.remove('sidebar-open');
            }
        });
    }

    /* --------------------------------------------------------------- Dropdowns */
    function initDropdowns() {
        document.addEventListener('click', function (event) {
            var trigger = event.target.closest('[data-dropdown-toggle]');
            var openMenus = document.querySelectorAll('.dropdown.is-open');

            for (var i = 0; i < openMenus.length; i++) {
                var menu = openMenus[i];
                if (menu.contains(event.target) && !trigger) continue;
                if (trigger && menu === trigger.closest('.dropdown')) continue;
                menu.classList.remove('is-open');
            }

            if (trigger) {
                event.preventDefault();
                var dropdown = trigger.closest('.dropdown');
                if (dropdown) dropdown.classList.toggle('is-open');
            }
        });

        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') return;
            var open = document.querySelectorAll('.dropdown.is-open');
            for (var i = 0; i < open.length; i++) open[i].classList.remove('is-open');
        });
    }

    /* ----------------------------------------------------------------- Filtros */
    function initFilters() {
        var panels = document.querySelectorAll('[data-filters]');

        for (var i = 0; i < panels.length; i++) {
            (function (panel) {
                var key = 'filters:' + (panel.dataset.filters || 'default');
                var hasActive = panel.querySelectorAll('[data-filter-chip]').length > 0;

                if (hasActive || localStorage.getItem(key) === '1') {
                    panel.classList.add('is-open');
                }

                var toggle = panel.querySelector('[data-filters-toggle]');
                if (!toggle) return;

                toggle.addEventListener('click', function () {
                    var open = panel.classList.toggle('is-open');
                    localStorage.setItem(key, open ? '1' : '0');
                });
            })(panels[i]);
        }
    }

    /* ------------------------------------------------------- Colunas da tabela */
    function initColumnPickers() {
        var pickers = document.querySelectorAll('[data-column-picker]');

        for (var i = 0; i < pickers.length; i++) {
            (function (picker) {
                var table = document.getElementById(picker.dataset.columnPicker);
                var list = picker.querySelector('[data-column-list]');
                if (!table || !table.tHead || !list) return;

                var storageKey = 'columns:' + table.id;
                var headers = table.tHead.rows[0].cells;
                var hidden = {};

                try {
                    hidden = JSON.parse(localStorage.getItem(storageKey) || '{}') || {};
                } catch (err) {
                    hidden = {};
                }

                function applyColumn(index, isHidden) {
                    var rows = table.rows;
                    for (var r = 0; r < rows.length; r++) {
                        var cell = rows[r].cells[index];
                        if (cell) cell.classList.toggle('is-hidden', isHidden);
                    }
                }

                function persist() {
                    localStorage.setItem(storageKey, JSON.stringify(hidden));
                    var count = Object.keys(hidden).filter(function (k) { return hidden[k]; }).length;
                    var badge = picker.querySelector('[data-column-count]');
                    if (badge) {
                        badge.textContent = count ? count : '';
                        badge.classList.toggle('is-hidden', count === 0);
                    }
                }

                for (var c = 0; c < headers.length; c++) {
                    var header = headers[c];
                    if (header.dataset.columnLock === '1') continue;

                    var label = document.createElement('label');
                    label.className = 'dropdown__item';

                    var input = document.createElement('input');
                    input.type = 'checkbox';
                    input.dataset.columnIndex = String(c);
                    input.checked = !hidden[c];

                    var text = document.createElement('span');
                    text.textContent = header.textContent.trim();

                    label.appendChild(input);
                    label.appendChild(text);
                    list.appendChild(label);

                    if (hidden[c]) applyColumn(c, true);
                }

                list.addEventListener('change', function (event) {
                    var input = event.target;
                    if (!input.dataset || input.dataset.columnIndex === undefined) return;
                    var index = parseInt(input.dataset.columnIndex, 10);
                    hidden[index] = !input.checked;
                    if (!hidden[index]) delete hidden[index];
                    applyColumn(index, !input.checked);
                    persist();
                });

                var reset = picker.querySelector('[data-column-reset]');
                if (reset) {
                    reset.addEventListener('click', function () {
                        var inputs = list.querySelectorAll('input[type="checkbox"]');
                        for (var k = 0; k < inputs.length; k++) {
                            inputs[k].checked = true;
                            applyColumn(parseInt(inputs[k].dataset.columnIndex, 10), false);
                        }
                        hidden = {};
                        persist();
                    });
                }

                persist();
            })(pickers[i]);
        }
    }

    /* ------------------------------------------------------------------ Modais */
    function initModals() {
        document.addEventListener('click', function (event) {
            var closer = event.target.closest('[data-modal-close]');
            if (closer) {
                var target = closer.getAttribute('data-modal-close');
                var modal = target ? document.getElementById(target) : closer.closest('.modal');
                if (modal) modal.classList.remove('is-open');
                return;
            }
            var opener = event.target.closest('[data-modal-open]');
            if (opener) {
                event.preventDefault();
                var modalOpen = document.getElementById(opener.getAttribute('data-modal-open'));
                if (modalOpen) modalOpen.classList.add('is-open');
                return;
            }
            if (event.target.classList && event.target.classList.contains('modal')) {
                event.target.classList.remove('is-open');
            }
        });

        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') return;
            var open = document.querySelectorAll('.modal.is-open');
            for (var i = 0; i < open.length; i++) open[i].classList.remove('is-open');
        });
    }

    /**
     * Abre o modal de texto longo (objeto, observação, histórico).
     */
    window.visualizarObservacao = function (conteudo, titulo) {
        var modal = document.getElementById('observacaoModal');
        if (!modal) return;
        var body = modal.querySelector('[data-modal-content]');
        var title = modal.querySelector('[data-modal-title]');
        if (body) body.textContent = conteudo;
        if (title && titulo) title.textContent = titulo;
        modal.classList.add('is-open');
    };

    window.fecharModal = function () {
        var modal = document.getElementById('observacaoModal');
        if (modal) modal.classList.remove('is-open');
    };

    /* ------------------------------------------------------------------ Cookie */
    window.getCookie = function (name) {
        if (!document.cookie) return null;
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === name + '=') {
                return decodeURIComponent(cookie.substring(name.length + 1));
            }
        }
        return null;
    };

    /* ---------------------------------------------------------- Tema claro/escuro */
    function isDarkTheme() {
        return document.documentElement.getAttribute('data-theme') === 'dark';
    }

    function updateThemeButtons() {
        var dark = isDarkTheme();
        var buttons = document.querySelectorAll('[data-theme-toggle]');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].setAttribute('aria-label', dark ? 'Ativar modo claro' : 'Ativar modo escuro');
            buttons[i].setAttribute('title', dark ? 'Modo claro' : 'Modo escuro');
            if (dark) {
                buttons[i].classList.add('is-dark');
            } else {
                buttons[i].classList.remove('is-dark');
            }
        }
    }

    function initTheme() {
        updateThemeButtons();

        document.addEventListener('click', function (event) {
            var toggle = event.target.closest('[data-theme-toggle]');
            if (!toggle) return;

            if (isDarkTheme()) {
                document.documentElement.removeAttribute('data-theme');
                localStorage.setItem('theme', 'light');
            } else {
                document.documentElement.setAttribute('data-theme', 'dark');
                localStorage.setItem('theme', 'dark');
            }
            updateThemeButtons();
        });
    }

    window.pedirMotivoFormulario = function (form, mensagem) {
        var motivo = window.prompt(mensagem);
        if (!motivo || !motivo.trim()) { return false; }
        var campo = form.querySelector('input[name="motivo"]');
        if (campo) { campo.value = motivo.trim(); }
        return true;
    };

    function initAnexos() {
        var inputs = document.querySelectorAll('.anexo-picker__input');
        for (var i = 0; i < inputs.length; i++) {
            inputs[i].addEventListener('change', function () {
                var rotulo = this.parentNode.querySelector('.anexo-picker__rotulo');
                if (!rotulo) return;
                var nomes = [];
                for (var j = 0; j < this.files.length; j++) {
                    nomes.push(this.files[j].name);
                }
                rotulo.textContent = nomes.length
                    ? nomes.join(', ')
                    : (rotulo.getAttribute('data-vazio') || 'Nenhum arquivo escolhido');
            });
        }
    }

    function initUrgencia() {
        var balao = document.getElementById('balao-urgencia');
        if (!balao) return;

        var formulario = null;
        var selectAberto = null;
        var ignorarClique = false;
        var numero = balao.querySelector('[data-balao-numero]');

        function fechar(restaurar) {
            balao.hidden = true;
            if (restaurar && selectAberto) {
                selectAberto.value = selectAberto.getAttribute('data-anterior') || selectAberto.value;
            }
            formulario = null;
            selectAberto = null;
        }

        function abrir(select) {
            formulario = select.form;
            selectAberto = select;
            var celula = select.closest('tr');
            var rotulo = celula ? celula.querySelector('.col-sticky strong') : null;
            numero.textContent = rotulo ? rotulo.textContent.trim() : 'deste número';
            balao.hidden = false;

            var caixa = select.getBoundingClientRect();
            var largura = balao.offsetWidth;
            var esquerda = Math.min(
                Math.max(8, caixa.left),
                window.innerWidth - largura - 8
            );
            var topo = caixa.bottom + 8;
            if (topo + balao.offsetHeight > window.innerHeight - 8) {
                topo = Math.max(8, caixa.top - balao.offsetHeight - 8);
            }
            balao.style.left = esquerda + 'px';
            balao.style.top = topo + 'px';
            ignorarClique = true;
            window.setTimeout(function () { ignorarClique = false; }, 0);
        }

        document.addEventListener('change', function (event) {
            var select = event.target.closest('.prio-form select[name="prioridade"]');
            if (!select) return;
            if (select.value === 'URGENTE') {
                abrir(select);
                return;
            }
            select.setAttribute('data-anterior', select.value);
            select.form.submit();
        });

        balao.addEventListener('click', function (event) {
            var botao = event.target.closest('[data-urgencia]');
            if (!botao || !formulario) return;
            var escolha = botao.getAttribute('data-urgencia');
            if (escolha === 'cancelar') {
                fechar(true);
                return;
            }
            var campo = formulario.querySelector('input[name="urgencia_recorrente"]');
            if (campo) campo.value = escolha;
            var alvo = formulario;
            fechar(false);
            alvo.submit();
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && !balao.hidden) fechar(true);
        });

        document.addEventListener('click', function (event) {
            if (balao.hidden || ignorarClique) return;
            if (event.target.closest('#balao-urgencia')) return;
            if (event.target.closest('.prio-form select[name="prioridade"]')) return;
            fechar(true);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initTheme();
        initSidebar();
        initDropdowns();
        initFilters();
        initColumnPickers();
        initModals();
        initAnexos();
        initUrgencia();
    });
})();
