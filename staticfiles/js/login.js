
document.addEventListener('DOMContentLoaded', () => {
  const form      = document.querySelector('form');
  const emailInp  = document.getElementById('email');
  const passInp   = document.getElementById('password');
  const rememberCb = document.getElementById('remember');
  const submitBtn = document.querySelector('.btn-submit');

  if (!form) return;

  /** Show an inline error below a field. */
  function setFieldError(inputEl, message) {
    clearFieldError(inputEl);
    inputEl.style.borderColor = '#c0392b';
    const err = document.createElement('p');
    err.className = '_auth-field-error';
    err.style.cssText = 'color:#c0392b;font-size:11px;margin-top:6px;letter-spacing:.04em;';
    err.textContent = message;
    inputEl.parentElement.appendChild(err);
  }

  function clearFieldError(inputEl) {
    inputEl.style.borderColor = '';
    const existing = inputEl.parentElement.querySelector('._auth-field-error');
    if (existing) existing.remove();
  }

  /** Show a top-level banner error (for non-field errors). */
  function showBanner(message, type = 'error') {
    removeBanner();
    const banner = document.createElement('div');
    banner.id = '_auth-banner';
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
    const b = document.getElementById('_auth-banner');
    if (b) b.remove();
  }

  function setLoading(loading) {
    submitBtn.disabled = loading;
    const inner = submitBtn.querySelector('span') || submitBtn;
    inner.style.opacity = loading ? '0.6' : '1';
  }

  // Show any server-injected messages (from email verification redirect)
  const verifySuccess = document.body.dataset.verifySuccess;
  const verifyError   = document.body.dataset.verifyError;
  if (verifySuccess) showBanner(verifySuccess, 'success');
  if (verifyError)   showBanner(verifyError,   'error');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    removeBanner();
    clearFieldError(emailInp);
    clearFieldError(passInp);

    setLoading(true);
    try {
      const data = await API.post('/account/login/', {
        email:       emailInp.value.trim(),
        password:    passInp.value,
        remember_me: rememberCb ? rememberCb.checked : false,
      });

      if (data.success) {
        showBanner('Signed in successfully. Redirecting…', 'success');
        setTimeout(() => API.goTo(data.redirect || '/shop/'), 600);
      } else {
        // Field-level errors
        if (data.errors) {
          if (data.errors.email)    setFieldError(emailInp, data.errors.email);
          if (data.errors.password) setFieldError(passInp,  data.errors.password);
        }
        if (data.error) showBanner(data.error);
      }
    } catch (err) {
      showBanner('Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  });

  // Clear errors on input
  [emailInp, passInp].forEach(el => {
    if (el) el.addEventListener('input', () => clearFieldError(el));
  });
});