
document.addEventListener('DOMContentLoaded', () => {
  const form      = document.getElementById('loginForm') || document.querySelector('form');
  const emailInp  = document.getElementById('email');
  const passInp   = document.getElementById('password');
  const rememberCb = document.getElementById('remember');
  const submitBtn = form ? form.querySelector('[type="submit"]') : null;

  if (!form || !emailInp || !passInp) return;

  function setError(fieldId, show) {
    const el = document.getElementById(fieldId);
    if (el) el.classList.toggle('has-error', show);
  }

  function showBanner(message, type = 'error') {
    removeBanner();
    const banner = document.createElement('div');
    banner.id = '_admin-banner';
    banner.style.cssText = `
      padding:14px 18px;margin-bottom:20px;font-size:13px;line-height:1.5;
      border-left:3px solid ${type === 'success' ? '#27ae60' : '#c0392b'};
      background:${type === 'success' ? '#f0faf4' : '#fdf3f2'};
      color:${type === 'success' ? '#27ae60' : '#c0392b'};
    `;
    banner.textContent = message;
    form.insertAdjacentElement('beforebegin', banner);
  }

  function removeBanner() {
    const b = document.getElementById('_admin-banner');
    if (b) b.remove();
  }

  function setLoading(loading) {
    if (submitBtn) submitBtn.disabled = loading;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    removeBanner();
    setError('fieldEmail',    false);
    setError('fieldPassword', false);

    const email    = emailInp.value.trim();
    const password = passInp.value;

    if (!email)    { setError('fieldEmail', true);    return; }
    if (!password) { setError('fieldPassword', true); return; }

    setLoading(true);
    try {
      const data = await API.post('/auth/admin/login/', {
        email,
        password,
        remember: rememberCb ? rememberCb.checked : false,
      });

      if (data.success) {
        showBanner('Authenticated. Redirecting to dashboard…', 'success');
        setTimeout(() => API.goTo(data.redirect || '/admin/'), 600);
      } else {
        showBanner(data.error || 'Invalid credentials.');
        if (data.errors?.email)    setError('fieldEmail',    true);
        if (data.errors?.password) setError('fieldPassword', true);
      }
    } catch (err) {
      showBanner('Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  });

  emailInp.addEventListener('input', () => setError('fieldEmail',    false));
  passInp.addEventListener('input',  () => setError('fieldPassword', false));
});