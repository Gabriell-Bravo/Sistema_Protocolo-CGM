// Roda só nas páginas /lai/ do sistema. Repassa os pedidos da página para a extensão e devolve a resposta.
(function () {
  document.documentElement.dataset.laiExtensao = chrome.runtime.getManifest().version;

  window.addEventListener('message', function (evento) {
    if (evento.source !== window) return;
    var d = evento.data;
    if (!d || d.laiExt !== 1 || d.direcao !== 'pagina') return;
    var responder = function (resposta) {
      window.postMessage({ laiExt: 1, direcao: 'extensao', id: d.id, resposta: resposta }, window.location.origin);
    };
    try {
      chrome.runtime.sendMessage({ tipo: d.tipo, dados: d.dados }, function (resposta) {
        if (chrome.runtime.lastError) responder({ ok: false, erro: chrome.runtime.lastError.message });
        else responder(resposta);
      });
    } catch (e) {
      responder({ ok: false, erro: 'A extensão foi atualizada. Recarregue a página.' });
    }
  });
})();
