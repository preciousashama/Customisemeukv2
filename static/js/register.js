
document.addEventListener('DOMContentLoaded', () => {
  const form      = document.querySelector('form');
  const nameInp   = document.getElementById('fullname');
  const emailInp  = document.getElementById('email');
  const passInp   = document.getElementById('password');
  const submitBtn = document.querySelector('.btn-submit');

  if (!form) return;

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
    if (!inputEl) return;
    inputEl.style.borderColor = '';
    const existing = inputEl.parentElement.querySelector('._auth-field-error');
    if (existing) existing.remove();
  }

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

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    removeBanner();
    [nameInp, emailInp, passInp].forEach(clearFieldError);

    // Client-side password confirmation check before hitting server
    const pw  = passInp ? passInp.value : '';
    const pw2Input = document.getElementById('password2') || document.getElementById('confirm-password');
    const pw2 = pw2Input ? pw2Input.value : pw;
    if (pw !== pw2) {
      if (pw2Input) setFieldError(pw2Input, 'Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      const data = await API.post('/auth/register/', {
        full_name: nameInp  ? nameInp.value.trim() : '',
        email:     emailInp ? emailInp.value.trim() : '',
        password:  pw,
        password2: pw2,
      });

      if (data.success) {
        showBanner(
          data.message || 'Registration successful! Please check your email to verify your account.',
          'success'
        );
        form.reset();
      } else {
        if (data.errors) {
          if (data.errors.full_name) setFieldError(nameInp,  data.errors.full_name);
          if (data.errors.email)     setFieldError(emailInp, data.errors.email);
          if (data.errors.password)  setFieldError(passInp,  data.errors.password);
          if (data.errors.password2 && pw2Input) setFieldError(pw2Input, data.errors.password2);
        }
        if (data.error) showBanner(data.error);
      }
    } catch (err) {
      showBanner('Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  });

  [nameInp, emailInp, passInp].forEach(el => {
    if (el) el.addEventListener('input', () => clearFieldError(el));
  });
});