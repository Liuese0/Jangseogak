// ══════════════════════════════════════════════════════
// 장서각 (Jangseogak) — Main JavaScript
// ══════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  initFlashAutoDismiss();
  initMobileNav();
  initSearchAutoSubmit();
  initPageTransitions();
});

// ── Flash auto-dismiss ──
function initFlashAutoDismiss() {
  const flashes = document.querySelectorAll('.flash-msg');
  flashes.forEach((flash, i) => {
    setTimeout(() => {
      flash.classList.add('fade-out');
      setTimeout(() => flash.remove(), 300);
    }, 5000 + i * 200);
  });
}

// ── Mobile hamburger ──
function initMobileNav() {
  const hamburger = document.getElementById('navHamburger');
  const panel = document.getElementById('navMobilePanel');
  const overlay = document.getElementById('navOverlay');
  if (!hamburger || !panel) return;

  const toggle = () => {
    panel.classList.toggle('open');
    overlay.classList.toggle('open');
  };

  hamburger.addEventListener('click', toggle);
  overlay.addEventListener('click', toggle);
}

// ── Search: submit form on radio change ──
function initSearchAutoSubmit() {
  const radios = document.querySelectorAll('.search-radio input[type="radio"]');
  radios.forEach(r => {
    r.addEventListener('change', e => {
      const form = e.target.closest('form');
      if (form && form.querySelector('input[name="q"]').value) {
        form.submit();
      }
    });
  });
}

// ── Page transitions ──
function initPageTransitions() {
  const wrapper = document.querySelector('.page-transition');
  if (wrapper) {
    wrapper.style.opacity = '0';
    requestAnimationFrame(() => {
      wrapper.style.opacity = '';
    });
  }
}

// ── QR Modal ──
function openQrModal(src, text) {
  const modal = document.getElementById('qrModal');
  const img = document.getElementById('qrModalImg');
  const txt = document.getElementById('qrModalText');
  if (!modal) return;
  img.src = src;
  txt.textContent = text || '';
  modal.classList.add('active');
}

function closeQrModal() {
  const modal = document.getElementById('qrModal');
  if (modal) modal.classList.remove('active');
}

// Click outside to close modal
document.addEventListener('click', e => {
  const modal = document.getElementById('qrModal');
  if (modal && e.target === modal) {
    closeQrModal();
  }
});

// Escape key to close modal
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeQrModal();
});
