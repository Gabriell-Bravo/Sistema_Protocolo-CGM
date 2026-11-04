chrome.runtime.sendMessage({ tipo: 'status' }, function (s) {
  var ponto = document.getElementById('p-fala');
  var texto = document.getElementById('t-fala');
  if (!s || s.ok === false) { texto.textContent = 'Não foi possível verificar.'; return; }
  ponto.className = 'ponto' + (s.online ? ' on' : '');
  texto.textContent = s.online ? 'Fala.BR online: ' + s.nome
    : (s.abaFalabr ? 'Fala.BR aberto, mas sem login' : 'Fala.BR não está aberto');
  document.getElementById('servidor').textContent = 'Sistema: ' + s.servidor + ' (versão ' + s.versao + ')';
});
