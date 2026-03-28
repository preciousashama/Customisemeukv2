
document.addEventListener('DOMContentLoaded', () => {
  const form      = document.querySelector('form');
  const submitBtn = form ? form.querySelector('[type="submit"], .submit-btn') : null;

  if (!form) return;

  function showBanner(message, type = 'success') {
    removeBanner();
    const banner = document.createElement('div');
    banner.id = '_contact-banner';
    banner.style.cssText = `
      padding:16px 20px;margin-bottom:24px;font-size:14px;line-height:1.6;
      border-left:3px solid ${type === 'success' ? '#27ae60' : '#c0392b'};
      background:${type === 'success' ? '#f0faf4' : '#fdf3f2'};
      color:${type === 'success' ? '#27ae60' : '#c0392b'};
    `;
    banner.textContent = message;
    form.insertAdjacentElement('beforebegin', banner);
    banner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function removeBanner() {
    const b = document.getElementById('_contact-banner');
    if (b) b.remove();
  }

  function setLoading(loading) {
    if (!submitBtn) return;
    submitBtn.disabled = loading;
    const span = submitBtn.querySelector('span') || submitBtn;
    span.style.opacity = loading ? '0.6' : '1';
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    removeBanner();

    const fields   = {};
    const formData = new FormData(form);
    formData.forEach((val, key) => { fields[key] = val; });

    // Basic required-field check client-side
    const required = ['full_name', 'email', 'message'];
    for (const key of required) {
      if (!fields[key] || !fields[key].toString().trim()) {
        showBanner('Please fill in all required fields.', 'error');
        return;
      }
    }

    setLoading(true);
    try {
      const data = await API.post('/auth/contact/', fields);
      if (data.success) {
        showBanner('Message sent! We\'ll get back to you within one business day.');
        form.reset();
      } else {
        showBanner(data.error || 'Something went wrong. Please try again.', 'error');
      }
    } catch {
      showBanner('Something went wrong. Please try again.', 'error');
    } finally {
      setLoading(false);
    }
  });
});