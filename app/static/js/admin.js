(function () {
  var csrf = (document.querySelector('meta[name=csrf-token]') || {}).content || '';

  // confirm dialogs on forms
  document.addEventListener('submit', function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute('data-confirm');
    if (msg && !confirm(msg)) e.preventDefault();
  });

  // copy-to-clipboard buttons
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-copy]');
    if (btn) {
      var text = btn.getAttribute('data-copy');
      var done = function () { var o = btn.textContent; btn.textContent = 'Copied ✓'; setTimeout(function () { btn.textContent = o; }, 1400); };
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done);
      else { var t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); done(); }
    }
    // WhatsApp buttons also mark the guest as "sent"
    var wa = e.target.closest('.wa[data-mark]');
    if (wa) {
      fetch(wa.getAttribute('data-mark'), { method: 'POST', headers: { 'X-CSRFToken': csrf }, keepalive: true });
      var row = wa.closest('tr, li');
      if (row) { var p = row.querySelector('.pill.warn'); if (p) { p.className = 'pill soft'; p.textContent = 'Sent'; } }
    }
    // colour presets
    var preset = e.target.closest('.preset');
    if (preset) {
      var t = JSON.parse(preset.getAttribute('data-theme'));
      Object.keys(t).forEach(function (k) { var f = document.querySelector('[name=' + k + ']'); if (f && k !== 'label') f.value = t[k]; });
    }
  });

  // gallery: upload photos one at a time so a big batch never exceeds the host's request-size limit
  document.querySelectorAll('form[data-seq-upload]').forEach(function (form) {
    form.addEventListener('submit', async function (e) {
      var input = form.querySelector('input[type=file]');
      if (!input.files.length || !window.fetch) return;
      e.preventDefault();
      var btn = form.querySelector('button[type=submit]'), files = Array.from(input.files), failed = 0;
      btn.disabled = true;
      for (var i = 0; i < files.length; i++) {
        btn.textContent = 'Uploading ' + (i + 1) + ' / ' + files.length + '…';
        var fd = new FormData(); fd.append('csrf_token', csrf); fd.append('photos', files[i]);
        try { var r = await fetch(form.action || location.href, { method: 'POST', body: fd, credentials: 'same-origin' }); if (!r.ok) failed++; } catch (err) { failed++; }
      }
      if (failed) alert(failed + ' photo(s) could not be uploaded (too large or not an image).');
      location.reload();
    });
  });

  // client-side image downscale before upload (keeps requests small on Vercel)
  document.querySelectorAll('input[type=file][data-compress]').forEach(function (input) {
    input.addEventListener('change', async function () {
      if (!window.DataTransfer || !input.files.length) return;
      var out = new DataTransfer();
      for (var f of input.files) {
        if (!/^image\/(jpeg|png|webp)$/.test(f.type) || f.size < 350 * 1024) { out.items.add(f); continue; }
        try {
          var bmp = await createImageBitmap(f);
          var scale = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
          var c = document.createElement('canvas'); c.width = Math.round(bmp.width * scale); c.height = Math.round(bmp.height * scale);
          c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
          var keepPng = f.type === 'image/png';
          var blob = await new Promise(function (r) { c.toBlob(r, keepPng ? 'image/png' : 'image/jpeg', 0.82); });
          out.items.add(blob && blob.size < f.size ? new File([blob], f.name, { type: blob.type }) : f);
        } catch (e) { out.items.add(f); }
      }
      input.files = out.files;
    });
  });
})();
