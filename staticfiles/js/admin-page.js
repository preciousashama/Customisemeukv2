
document.addEventListener('DOMContentLoaded', async () => {
  try {
    const data = await API.get('/auth/admin/dashboard-data/');
    if (!data.success) {
      // Not authenticated or not admin — redirect
      API.goTo('/admin-login/');
      return;
    }

    // Populate current admin name if a placeholder exists
    const nameEl = document.getElementById('admin-name');
    if (nameEl && data.current_admin) {
      nameEl.textContent = data.current_admin.name || data.current_admin.email;
    }

    // Populate stats if stat elements exist (optional — add ids to admin-page.html)
    const statsMap = {
      'stat-total-customers':      data.users.total_customers,
      'stat-verified-customers':   data.users.verified_customers,
      'stat-unverified-customers': data.users.unverified_customers,
      'stat-total-admins':         data.users.total_admins,
    };
    Object.entries(statsMap).forEach(([id, val]) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    });

  } catch (err) {
    console.error('Dashboard data load failed:', err);
  }
});

/** Logout button helper — call from the admin page. */
async function adminLogout() {
  const data = await API.post('/auth/logout/');
  if (data.success) API.goTo(data.redirect || '/admin-login/');
}

window.adminLogout = adminLogout;