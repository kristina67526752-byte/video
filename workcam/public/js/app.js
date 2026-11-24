/* Work.cam — petites améliorations progressives (le site fonctionne aussi sans JavaScript). */
(function () {
  'use strict';

  // Confirmation avant actions sensibles
  document.addEventListener('submit', function (e) {
    var f = e.target;
    var msg = f.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) { e.preventDefault(); return; }
    var btn = f.querySelector('button[data-loading]');
    if (btn) { btn.disabled = true; btn.textContent = btn.getAttribute('data-loading'); }
  });

  // Aperçu de la photo avant envoi
  var input = document.getElementById('photo');
  if (input) {
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      var img = document.getElementById('photopreview');
      var hint = document.getElementById('photohint');
      if (!file || !img) return;
      img.src = URL.createObjectURL(file);
      img.hidden = false;
      if (hint) hint.hidden = true;
    });
  }

  // Suivi du paiement Mobile Money
  var pay = document.getElementById('paystatus');
  if (pay && pay.getAttribute('data-status') === 'pending') {
    var id = pay.getAttribute('data-id');
    var tries = 0;
    var poll = function () {
      tries++;
      fetch('/api/payments/' + id + '/status', { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.status && d.status !== 'pending') { window.location.reload(); return; }
          if (tries < 240) setTimeout(poll, tries < 20 ? 3000 : 6000);
        })
        .catch(function () { if (tries < 240) setTimeout(poll, 8000); });
    };
    setTimeout(poll, 3000);
  }

  // Messagerie : envoi sans rechargement + réception par polling
  var thread = document.getElementById('thread');
  if (thread) {
    var conv = thread.getAttribute('data-conv');
    var last = parseInt(thread.getAttribute('data-last'), 10) || 0;
    var box = document.getElementById('msgs');
    var form = document.getElementById('composer');
    var seen = {};
    var fmt = function (iso) {
      var d = new Date(iso);
      return d.toLocaleString(document.documentElement.lang === 'en' ? 'en-GB' : 'fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    };
    var add = function (m) {
      if (seen[m.id] || document.getElementById('m' + m.id)) return;
      seen[m.id] = true;
      var empty = document.getElementById('nomsg'); if (empty) empty.remove();
      var div = document.createElement('div');
      div.className = 'msg' + (m.mine ? ' msg--me' : '');
      div.id = 'm' + m.id;
      var p = document.createElement('p'); p.textContent = m.body;
      var t = document.createElement('time'); t.textContent = fmt(m.at);
      div.appendChild(p); div.appendChild(t);
      box.appendChild(div);
      if (m.id > last) last = m.id;
      box.scrollTop = box.scrollHeight;
    };
    box.scrollTop = box.scrollHeight;

    if (form) {
      var ta = form.querySelector('textarea');
      ta.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey && window.matchMedia('(pointer:fine)').matches) { e.preventDefault(); form.requestSubmit(); }
      });
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var body = ta.value.trim();
        if (!body) return;
        var btn = form.querySelector('button'); btn.disabled = true;
        fetch(form.action, {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: new URLSearchParams(new FormData(form)).toString(),
        }).then(function (r) { return r.json(); })
          .then(function (d) { if (d.message) { add(d.message); ta.value = ''; } })
          .catch(function () { form.submit(); })
          .finally(function () { btn.disabled = false; ta.focus(); });
      });
    }

    var tick = function () {
      if (document.hidden) { setTimeout(tick, 5000); return; }
      fetch('/api/messages/' + conv + '?after=' + last, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) { (d.messages || []).forEach(add); })
        .catch(function () {})
        .finally(function () { setTimeout(tick, 5000); });
    };
    setTimeout(tick, 5000);
  }
})();
