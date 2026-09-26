// Comportamentos simples das páginas. Sem dependências.

// Formulários com data-aplicar-ao-mudar são enviados assim que um campo muda
// (filtros de alertas e escolha do mês do relatório). O botão de envio fica num
// <noscript>, só para quem estiver sem JavaScript.
//
// Só envia se o campo alterado for válido: ao digitar o ano num campo de data, o
// navegador dispara "change" a cada dígito (0002, 0020, 0202...); com min="1900-01-01"
// esses valores são inválidos e o envio espera o ano completo.
document.querySelectorAll('form[data-aplicar-ao-mudar]').forEach((formulario) => {
  formulario.addEventListener('change', (evento) => {
    const campo = evento.target;
    if (typeof campo.checkValidity === 'function' && !campo.checkValidity()) {
      return;
    }
    if (typeof formulario.requestSubmit === 'function') {
      formulario.requestSubmit();
    } else {
      formulario.submit();
    }
  });
});
