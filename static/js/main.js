document.addEventListener('DOMContentLoaded', function () {

  // Toggle sidebar
  const sidebar = document.getElementById('sidebar');
  const topbar  = document.getElementById('topbar');
  const content = document.getElementById('mainContent');
  document.getElementById('btnToggle')?.addEventListener('click', function () {
    sidebar.classList.toggle('collapsed');
    topbar.classList.toggle('collapsed');
    content.classList.toggle('collapsed');
  });

  // Submenus
  document.querySelectorAll('.nav-item[data-sub]').forEach(function (item) {
    item.addEventListener('click', function (e) {
      e.preventDefault();
      const sub = document.getElementById(item.getAttribute('data-sub'));
      if (!sub) return;
      item.classList.toggle('open');
      sub.classList.toggle('open');
    });
  });

  // Cards colapsáveis
  document.querySelectorAll('.card-panel-header').forEach(function (h) {
    h.addEventListener('click', function () {
      const body = h.nextElementSibling;
      if (!body) return;
      body.classList.toggle('hidden');
      const ico = h.querySelector('.toggle-btn i');
      if (ico) {
        ico.classList.toggle('fa-chevron-up');
        ico.classList.toggle('fa-chevron-down');
      }
    });
  });

  // Confirm delete
  document.querySelectorAll('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      if (!confirm(f.getAttribute('data-confirm') || 'Confirmar?')) e.preventDefault();
    });
  });

  // Auto-dismiss flash
  setTimeout(function () {
    document.querySelectorAll('.flash-msg').forEach(function (el) {
      el.style.transition = 'opacity .5s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    });
  }, 4000);

  // Preview cálculo impostos
  const vBruto = document.getElementById('valor_bruto');
  if (vBruto) {
    vBruto.addEventListener('input', calcPreview);
    calcPreview();
  }
  function calcPreview() {
    const v   = parseFloat(document.getElementById('valor_bruto')?.value) || 0;
    const imp = parseFloat(document.getElementById('taxa_imposto')?.value) || 0;
    const com = parseFloat(document.getElementById('taxa_comissao')?.value) || 0;
    const deducoes = v * (imp / 100);
    const comissao = v * (com / 100);
    const liquido  = v - deducoes - comissao;
    const el = document.getElementById('previewLiquido');
    if (el) el.textContent = 'R$ ' + liquido.toLocaleString('pt-BR', {minimumFractionDigits:2});
  }

});
