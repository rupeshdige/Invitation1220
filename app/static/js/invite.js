(function () {
  var body = document.body;
  var envScreen = document.getElementById('envelope-screen');
  var envelope = document.getElementById('envelope');
  var card = document.getElementById('card');
  var preview = body.dataset.preview === '1';
  var storeKey = 'inv-open-' + body.dataset.slug;

  function reveal() {
    card.hidden = false;
    var els = card.querySelectorAll('.reveal');
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
      }, { threshold: 0.12 });
      els.forEach(function (el) { io.observe(el); });
    } else { els.forEach(function (el) { el.classList.add('in'); }); }
    window.scrollTo(0, 0);
  }

  function track() {
    if (preview || !body.dataset.openedUrl) return;
    try { fetch(body.dataset.openedUrl, { method: 'POST', keepalive: true }); } catch (e) {}
  }

  function openCard(animate) {
    if (!animate) { envScreen.hidden = true; reveal(); return; }
    envScreen.classList.add('opening');
    requestAnimationFrame(function () { envelope.classList.add('open'); });
    try { sessionStorage.setItem(storeKey, '1'); } catch (e) {}
    setTimeout(function () { envScreen.classList.add('leaving'); }, 1150);
    setTimeout(function () {
      envScreen.hidden = true;
      reveal();
      setTimeout(track, 400); // network call only after the animation is done
    }, 1550);
  }

  // warm up: decode card images while the envelope is on screen so the reveal is not janky
  card.querySelectorAll('img:not([loading="lazy"])').forEach(function (img) {
    if (img.decode) img.decode().catch(function () {});
  });

  var seen = false;
  try { seen = sessionStorage.getItem(storeKey) === '1'; } catch (e) {}
  if (seen) { openCard(false); } else { envelope.addEventListener('click', function () { openCard(true); }, { once: true }); }

  // ----- countdown -----
  var cd = document.querySelector('.countdown');
  if (cd) {
    var target = new Date(cd.dataset.target).getTime();
    var u = { d: cd.querySelector('[data-u=d]'), h: cd.querySelector('[data-u=h]'), m: cd.querySelector('[data-u=m]'), s: cd.querySelector('[data-u=s]') };
    var tick = function () {
      var diff = Math.max(0, target - Date.now()), sec = Math.floor(diff / 1000);
      u.d.textContent = Math.floor(sec / 86400); u.h.textContent = Math.floor(sec % 86400 / 3600);
      u.m.textContent = Math.floor(sec % 3600 / 60); u.s.textContent = sec % 60;
      if (!diff) cd.hidden = true;
    };
    if (isNaN(target)) cd.hidden = true; else { tick(); setInterval(tick, 1000); }
  }

  // preview-only buttons
  document.querySelectorAll('[data-preview-only]').forEach(function (a) {
    a.addEventListener('click', function (e) { e.preventDefault(); alert('This works on each guest\'s personal link.'); });
  });

  // ----- RSVP -----
  var form = document.getElementById('rsvp-form');
  if (!form) return;
  var thanks = document.getElementById('thanks');
  var errBox = document.getElementById('rsvp-error');

  form.querySelectorAll('.rsvp-row').forEach(function (row) {
    var max = parseInt(row.dataset.max, 10) || 1;
    var out = row.querySelector('output');
    var dec = row.querySelector('.dec');
    var inc = row.querySelector('.inc');
    function sync() {
      var v = parseInt(out.textContent, 10) || 0;
      dec.disabled = v <= 0; inc.disabled = v >= max;
    }
    dec.addEventListener('click', function () { out.textContent = Math.max(0, (parseInt(out.textContent, 10) || 0) - 1); sync(); });
    inc.addEventListener('click', function () { out.textContent = Math.min(max, (parseInt(out.textContent, 10) || 0) + 1); sync(); });
    sync();
  });

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    errBox.hidden = true;
    var counts = {}, total = 0, single = 0;
    form.querySelectorAll('.rsvp-row').forEach(function (row) {
      var v = parseInt(row.querySelector('output').textContent, 10) || 0;
      if (row.dataset.fn === 'count') single = v; else counts[row.dataset.fn] = v;
      total += v;
    });
    var btn = form.querySelector('.send');
    if (total === 0 && !confirm('You have chosen 0 for every function, so we will record that you are unable to attend. Continue?')) return;

    if (preview) { form.hidden = true; thanks.hidden = false; confetti(); return; }
    btn.disabled = true; btn.textContent = 'Sending…';
    fetch(body.dataset.rsvpUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ functions: counts, count: single, note: form.note.value })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok || !res.j.ok) throw new Error(res.j.error || 'Something went wrong. Please try again.');
        form.hidden = true; thanks.hidden = false; if (total > 0) confetti(); thanks.scrollIntoView({ behavior: 'smooth', block: 'center' });
      })
      .catch(function (e) { errBox.textContent = e.message; errBox.hidden = false; })
      .finally(function () { btn.disabled = false; btn.textContent = 'Send RSVP'; });
  });

  // wishes: quick chips + counter
  var wish = document.getElementById('wish-text'), wc = document.getElementById('wish-count');
  if (wish) {
    var upd = function () { wc.textContent = wish.value.length; };
    wish.addEventListener('input', upd); upd();
    form.querySelectorAll('.chip').forEach(function (c) {
      c.addEventListener('click', function () {
        var t = c.dataset.text; wish.value = (wish.value.trim() ? wish.value.trim() + ' ' : '') + t;
        wish.value = wish.value.slice(0, 1000); upd(); wish.focus();
      });
    });
  }

  function confetti() {
    var cols = [getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#a8863c', '#f3e3a6', '#ffffff', '#e8c26b'];
    for (var i = 0; i < 70; i++) {
      var c = document.createElement('i'); c.className = 'confetti';
      c.style.left = Math.random() * 100 + 'vw'; c.style.background = cols[i % cols.length];
      c.style.setProperty('--dx', (Math.random() * 160 - 80) + 'px');
      c.style.animationDuration = (2.2 + Math.random() * 2) + 's'; c.style.animationDelay = Math.random() * .5 + 's';
      document.body.appendChild(c); setTimeout(function (el) { el.remove(); }.bind(null, c), 5200);
    }
  }

  var change = document.getElementById('change-reply');
  if (change) change.addEventListener('click', function () { thanks.hidden = true; form.hidden = false; });
})();
