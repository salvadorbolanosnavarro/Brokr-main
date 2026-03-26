/* ═══════════════════════════════════════════════════════════
   BROKR® — Router de paneles
   ═══════════════════════════════════════════════════════════
   Controla qué panel/módulo se muestra.
   
   PARA AGREGAR UN MÓDULO NUEVO:
   1. Agrega una entrada en MODULES con el ID y la etiqueta
   2. Agrega el HTML del panel en index.html con class="panel"
   3. Agrega el botón en el sidebar con data-module="tu-modulo"
   4. Listo — no necesitas tocar nada más
   ═══════════════════════════════════════════════════════════ */

// ── REGISTRO DE MÓDULOS ──
// Cada módulo tiene:
//   id     → el ID del elemento panel en el HTML
//   label  → lo que aparece en el header
//   type   → 'embedded' (vive en el HTML) o 'iframe' (archivo separado)
const MODULES = {
  'home':          { id: 'dashboard',          label: '',                      type: 'embedded' },
  'ficha-manual':  { id: 'panel-ficha-manual',  label: 'Fichas manuales',       type: 'iframe' },
  'ficha':         { id: 'panel-ficha',         label: 'Fichas EasyBroker',     type: 'iframe' },
  'contratos':     { id: 'panel-contratos',     label: 'Contratos',             type: 'iframe' },
  'avm':           { id: 'panel-avm',           label: 'Opinión de valor',      type: 'iframe' },
  'isr':           { id: 'panel-isr',           label: 'Calculadora ISR',       type: 'iframe' },
  'props':         { id: 'panel-props',         label: 'Mis inmuebles',         type: 'iframe' },
  // ─── AGREGAR MÓDULOS NUEVOS AQUÍ ───
  // 'usuario':    { id: 'panel-usuario',       label: 'Mi cuenta',             type: 'iframe' },
  // 'crm':       { id: 'panel-crm',           label: 'CRM',                   type: 'iframe' },
};

let _currentPanel = 'home';

// ── NAVEGAR A UN PANEL ──
function setPanel(name) {
  const module = MODULES[name];
  if (!module) {
    console.warn(`Módulo "${name}" no registrado en el router`);
    return;
  }

  // Ocultar TODOS los paneles
  document.querySelectorAll('.panel').forEach(p => {
    p.classList.remove('active');
  });

  // Mostrar el panel seleccionado
  const el = document.getElementById(module.id);
  if (el) {
    el.classList.add('active');
  }

  // Actualizar header
  const lbl = document.getElementById('hlbl');
  if (lbl) lbl.textContent = module.label;

  // Actualizar sidebar — marcar botón activo
  document.querySelectorAll('.sb-btn').forEach(b => b.classList.remove('active'));
  const activeBtn = document.querySelector(`.sb-btn[data-module="${name}"]`);
  if (activeBtn) activeBtn.classList.add('active');

  // Guardar estado actual
  _currentPanel = name;

  // Aplicar permisos si están cargados
  if (typeof applyUserPermissions === 'function') applyUserPermissions();

  // Cerrar sidebar en móvil
  if (window.innerWidth <= 767) closeSidebar();
}

// ── ATAJOS DE NAVEGACIÓN ──
function showDashboard() { setPanel('home'); }
function goISR()         { setPanel('isr'); }
function goProps()       { setPanel('props'); }

// ── SIDEBAR TOGGLE (MOBILE) ──
function toggleSidebar() {
  const sb = document.getElementById('sb');
  const ov = document.getElementById('sb-overlay');
  sb.classList.toggle('open');
  ov.classList.toggle('show');
}

function closeSidebar() {
  const sb = document.getElementById('sb');
  const ov = document.getElementById('sb-overlay');
  sb.classList.remove('open');
  ov.classList.remove('show');
}

// ── CHAT FLOTANTE ──
function toggleChatFloat() {
  const win = document.getElementById('chat-window');
  const fab = document.getElementById('chat-fab');
  const ov  = document.getElementById('chat-overlay');
  const isOpen = win && win.classList.contains('open');
  
  if (isOpen) {
    if (win) win.classList.remove('open');
    if (fab) fab.classList.remove('open');
    if (ov) ov.classList.remove('show');
  } else {
    if (win) win.classList.add('open');
    if (fab) fab.classList.add('open');
    if (ov) ov.classList.add('show');
  }
}

function closeChatFloat() {
  document.getElementById('chat-window')?.classList.remove('open');
  document.getElementById('chat-fab')?.classList.remove('open');
  document.getElementById('chat-overlay')?.classList.remove('show');
}

// ── INIT ──
document.addEventListener('DOMContentLoaded', async () => {
  // 1. Autenticar
  await authInit();
  
  // 2. Actualizar UI con datos de usuario
  updateUserDisplay();
  
  // 3. Aplicar permisos
  applyUserPermissions();
  
  // 4. Mostrar dashboard
  showDashboard();
});
