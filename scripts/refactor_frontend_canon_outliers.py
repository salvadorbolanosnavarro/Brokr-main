#!/usr/bin/env python3
"""Deterministically migrate the last active frontend Canon outliers.

Only presentation/iconography is changed. IDs, handlers, API calls and business logic
remain untouched. The script is intentionally strict and aborts if expected legacy
patterns are not present exactly once.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def write(name, text):
    (ROOT / name).write_text(text, encoding="utf-8")


def sub_once(text, pattern, repl, label, flags=0):
    out, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {n}")
    return out


# 1) ISR: CTA uses action blue; black remains text only.
isr = read("isr.html")
isr = sub_once(
    isr,
    r"(\.btn-calc\s*\{.*?\bbackground:\s*)var\(--ink\)(;)",
    r"\1var(--sky-blue)\2",
    "ISR primary calculate button",
    re.S,
)
isr = sub_once(
    isr,
    r"(\.btn-calc \.btn-teal-line\s*\{.*?\bbackground:\s*)var\(--ink\)(;)",
    r"\1var(--sky-blue-lift)\2",
    "ISR calculate accent line",
    re.S,
)
write("isr.html", isr)


# 2) Bandeja: one fixed type size + legacy close glyph.
bandeja = read("bandeja.html")
old = ".bx-avisos__no{flex:none;border:0;background:transparent;cursor:pointer;color:var(--mute);font-size:13px;padding:2px 4px}"
new = ".bx-avisos__no{flex:none;border:0;background:transparent;cursor:pointer;color:var(--mute);font-size:var(--fs-xs);padding:2px 4px}"
if bandeja.count(old) != 1:
    raise RuntimeError(f"Bandeja fixed font-size: expected 1 exact match, got {bandeja.count(old)}")
bandeja = bandeja.replace(old, new)
if bandeja.count("✕") != 1:
    raise RuntimeError(f"Bandeja close glyph: expected 1 match, got {bandeja.count('✕')}")
bandeja = bandeja.replace("✕", "Cerrar")
write("bandeja.html", bandeja)


# 3) Legal: retain every legal word and tab behavior, replace only its legacy skin.
legal = read("legal.html")
LEGAL_CSS = r'''<style>
*, *::before, *::after { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0; background: var(--paper); color: var(--ink);
  font-family: var(--font-sans); font-size: var(--fs-sm); line-height: var(--lh);
  -webkit-font-smoothing: antialiased;
}
.tab-nav {
  position: sticky; top: 0; z-index: var(--z-nav); background: var(--glass-bg);
  backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur);
  border-bottom: 1px solid var(--line); padding: 0 var(--sp-4);
  display: flex; gap: var(--sp-1); overflow-x: auto; -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.tab-nav::-webkit-scrollbar { display: none; }
.tab-btn {
  flex-shrink: 0; padding: var(--sp-4) var(--sp-5) var(--sp-3); border: none;
  background: none; cursor: pointer; font: 600 var(--fs-xs) var(--font-sans);
  color: var(--mute); border-bottom: 2px solid transparent; margin-bottom: -1px;
  transition: color var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease);
  white-space: nowrap;
}
.tab-btn.active { color: var(--sky-blue); border-bottom-color: var(--sky-blue); }
.tab-btn:hover:not(.active) { color: var(--ink); }
.tab-btn:focus-visible { outline: none; box-shadow: var(--focus); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.doc-wrap { max-width: var(--form-max); margin: 0 auto; padding: var(--sp-8) var(--sp-6) var(--sp-20); }
.doc-title {
  font: 800 var(--fs-h2) var(--font-display); color: var(--ink); margin: 0 0 var(--sp-1);
  text-align: center; letter-spacing: -0.02em;
}
.doc-subtitle { font-size: var(--fs-sm); color: var(--mute); text-align: center; font-style: italic; margin: 0 0 var(--sp-1); }
.doc-date { font-size: var(--fs-xs); color: var(--mute); text-align: center; margin: 0 0 var(--sp-7); }
.h1 {
  font-size: var(--fs-xs); font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--sky-blue); margin: var(--sp-7) 0 var(--sp-3); padding-bottom: var(--sp-2);
  border-bottom: 1px solid var(--line);
}
.h2 { font-size: var(--fs-sm); font-weight: 700; color: var(--sky-navy); margin: var(--sp-5) 0 var(--sp-2); }
p { margin: 0 0 var(--sp-3); color: var(--ink-2); text-align: justify; }
p.center { text-align: center; }
ul { margin: 0 0 var(--sp-3); padding-left: var(--sp-6); }
ul li { margin-bottom: var(--sp-2); color: var(--ink-2); text-align: justify; }
b, strong { color: var(--ink); }
.notice-banner {
  background: var(--sky-canvas); border: 1px solid var(--line-2); border-radius: var(--r);
  padding: var(--sp-4) var(--sp-5); margin-bottom: var(--sp-7); font-size: var(--fs-xs);
  color: var(--ink-2); line-height: var(--lh);
}
.notice-banner strong { color: var(--sky-navy); }
.aviso-final {
  text-align: center; color: var(--mute); font-size: var(--fs-xs); margin-top: var(--sp-8);
  padding-top: var(--sp-6); border-top: 1px solid var(--line);
}
@media (max-width: 600px) {
  .doc-wrap { padding: var(--sp-6) var(--sp-4) var(--sp-12); }
  .doc-title { font-size: var(--fs-h5); }
  .tab-btn { padding: var(--sp-3) var(--sp-4); font-size: var(--fs-label-3); }
}
</style>'''
legal = sub_once(legal, r"<style>.*?</style>", LEGAL_CSS, "Legal skin", re.S)
write("legal.html", legal)


# 4) Verificador: preserve checklist/AI behavior, replace the entire legacy skin
# and remove emoji iconography from the UI/prompt. Existing class names stay intact.
ver = read("verificador.html")
VER_CSS = r'''<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-sans);background:var(--paper);color:var(--ink);min-height:100vh}
.top-header{background:var(--bone);border-bottom:1px solid var(--line);padding:var(--sp-4) var(--sp-5);position:sticky;top:0;z-index:var(--z-nav)}
.top-header h1{font-family:var(--font-display);font-size:var(--fs-h2);color:var(--ink);margin-bottom:var(--sp-1)}
.top-header p{font-size:var(--fs-label-3);color:var(--mute);line-height:var(--lh-snug)}
.tipo-selector{display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-3);padding:var(--sp-4) var(--sp-5) 0}
.tipo-btn{padding:var(--sp-4) var(--sp-3);border:1px solid var(--line-2);border-radius:var(--r);background:var(--bone);cursor:pointer;text-align:center;font-family:var(--font-sans);transition:border-color var(--dur-fast) var(--ease),background var(--dur-fast) var(--ease),color var(--dur-fast) var(--ease)}
.tipo-btn:hover{border-color:var(--sky-blue);background:var(--sky-canvas)}
.tipo-btn.active{border-color:var(--sky-navy);background:var(--sky-navy);color:#fff}
.tipo-ico{font-size:var(--fs-label-3);font-weight:800;letter-spacing:.04em;margin-bottom:var(--sp-1);color:var(--sky-blue)}
.tipo-btn.active .tipo-ico{color:var(--sky-blue-on-dark)}
.tipo-lbl{font-size:var(--fs-xs);font-weight:700;display:block;color:var(--ink)}
.tipo-btn.active .tipo-lbl{color:#fff}
.tipo-sub{font-size:var(--fs-caption);color:var(--mute);margin-top:var(--sp-1);display:block}
.tipo-btn.active .tipo-sub{color:var(--sky-blue-on-dark)}
.progress-card{background:var(--bone);border:1px solid var(--line);border-radius:var(--r);margin:var(--sp-4) var(--sp-5) 0;padding:var(--sp-4) var(--sp-5)}
.progress-top{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-3);margin-bottom:var(--sp-3)}
.progress-label{font-size:var(--fs-xs);font-weight:700;color:var(--ink)}
.progress-counts{display:flex;gap:var(--sp-3);flex-wrap:wrap}.pc{font-size:var(--fs-caption);font-weight:700}.pc.ok{color:var(--success)}.pc.warn{color:var(--warn)}.pc.bad{color:var(--danger)}.pc.pend{color:var(--mute)}
.progress-bar-wrap{height:var(--sp-2);background:var(--paper-2);border-radius:var(--r-pill);overflow:hidden}.progress-bar-fill{height:100%;border-radius:var(--r-pill);background:var(--success);transition:width var(--dur-slow) var(--ease)}
.progress-reset{font-size:var(--fs-caption);color:var(--mute);cursor:pointer;text-decoration:underline;margin-top:var(--sp-2);display:inline-block}.progress-reset:hover{color:var(--danger)}
.doc-section{margin:var(--sp-4) var(--sp-5) 0}.section-hdr{display:flex;align-items:center;gap:var(--sp-2);margin-bottom:var(--sp-2)}.section-hdr-ico{font-size:var(--fs-caption);font-weight:800;color:var(--sky-blue);min-width:var(--sp-8)}.section-hdr-lbl{font-size:var(--fs-h5);font-weight:800;letter-spacing:-.01em;color:var(--ink)}.section-hdr-line{flex:1;height:1px;background:var(--line)}
.doc-item{background:var(--bone);border:1px solid var(--line);border-radius:var(--r);margin-bottom:var(--sp-2);overflow:hidden;transition:border-color var(--dur-fast) var(--ease),box-shadow var(--dur-fast) var(--ease)}
.doc-item.approved{border-color:var(--success)}.doc-item.attention{border-color:var(--warn)}.doc-item.rejected{border-color:var(--danger)}.doc-item.manual{border-color:var(--sky-blue)}
.doc-item-head{display:flex;align-items:center;gap:var(--sp-3);padding:var(--sp-3) var(--sp-4);cursor:pointer;user-select:none}.doc-status-ico{font-size:var(--fs-caption);font-weight:800;flex-shrink:0;min-width:var(--sp-7);text-align:center;color:var(--mute)}.doc-status-ico.spin{animation:spinIcon .8s linear infinite;display:inline-block}@keyframes spinIcon{to{transform:rotate(360deg)}}
.doc-head-info{flex:1;min-width:0}.doc-head-name{font-size:var(--fs-sm);font-weight:700;color:var(--ink)}.doc-head-sub{font-size:var(--fs-caption);color:var(--mute);margin-top:var(--sp-1)}.doc-chevron{color:var(--mute);font-size:var(--fs-xs);transition:transform var(--dur-fast) var(--ease);flex-shrink:0}.doc-item.open .doc-chevron{transform:rotate(180deg)}.doc-optional-tag{font-size:var(--fs-caption);font-weight:700;letter-spacing:.04em;background:var(--paper-2);color:var(--mute);border-radius:var(--r-sm);padding:var(--sp-1) var(--sp-2);margin-left:var(--sp-2);vertical-align:middle}
.doc-body{display:none;padding:0 var(--sp-4) var(--sp-4);border-top:1px solid var(--line)}.doc-item.open .doc-body{display:block}.doc-desc{font-size:var(--fs-label-3);color:var(--ink-2);line-height:var(--lh);margin:var(--sp-3) 0;padding:var(--sp-3);background:var(--paper-2);border-radius:var(--r-sm)}
.upload-zone{border:1px dashed var(--line-2);border-radius:var(--r);padding:var(--sp-6);text-align:center;cursor:pointer;transition:border-color var(--dur-fast) var(--ease),background var(--dur-fast) var(--ease);background:var(--paper-2);margin-bottom:var(--sp-3);position:relative}.upload-zone:hover,.upload-zone.drag{border-color:var(--sky-blue);background:var(--sky-canvas)}.upload-zone.has-file{border-color:var(--success);background:var(--success-soft);border-style:solid}.upload-ico{font-size:var(--fs-xs);font-weight:800;color:var(--sky-blue);margin-bottom:var(--sp-2)}.upload-lbl{font-size:var(--fs-xs);font-weight:700;color:var(--ink)}.upload-sub{font-size:var(--fs-caption);color:var(--mute);margin-top:var(--sp-1)}.upload-file-input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}.upload-preview{width:100%;max-height:200px;object-fit:contain;border-radius:var(--r);margin-bottom:var(--sp-3);border:1px solid var(--line);display:none}.upload-preview.show{display:block}.upload-change-btn{font-size:var(--fs-caption);color:var(--sky-blue);cursor:pointer;text-decoration:underline;display:block;text-align:center;margin-bottom:var(--sp-2)}
.doc-actions{display:flex;gap:var(--sp-2);margin-bottom:var(--sp-3);flex-wrap:wrap}.doc-btn{padding:var(--sp-2) var(--sp-4);border-radius:var(--r-sm);border:none;font-family:var(--font-sans);font-size:var(--fs-label-3);font-weight:700;cursor:pointer;display:flex;align-items:center;gap:var(--sp-2);transition:background var(--dur-fast) var(--ease),border-color var(--dur-fast) var(--ease),color var(--dur-fast) var(--ease)}.doc-btn.ai{background:var(--sky-blue);color:#fff}.doc-btn.ai:hover{background:var(--sky-blue-press)}.doc-btn.ai:disabled{background:var(--line-2);color:var(--mute);cursor:not-allowed}.doc-btn.manual{background:var(--paper-2);color:var(--ink);border:1px solid var(--line)}.doc-btn.manual:hover{border-color:var(--sky-blue);background:var(--sky-canvas);color:var(--sky-blue)}.doc-btn.clear{background:var(--paper-2);color:var(--mute);border:1px solid var(--line)}.doc-btn.clear:hover{border-color:var(--danger);color:var(--danger)}
.ai-result{border-radius:var(--r-sm);padding:var(--sp-3) var(--sp-4);font-size:var(--fs-label-3);line-height:var(--lh);white-space:pre-wrap;display:none;margin-top:var(--sp-2)}.ai-result.show{display:block}.ai-result.approved{background:var(--success-soft);border:1px solid var(--success);color:var(--success)}.ai-result.attention{background:var(--warn-soft);border:1px solid var(--warn);color:var(--warn)}.ai-result.rejected{background:var(--danger-soft);border:1px solid var(--danger);color:var(--danger)}.ai-result.manual{background:var(--info-soft);border:1px solid var(--info);color:var(--info)}.ai-verdict{font-size:var(--fs-h2);font-weight:800;letter-spacing:-.01em;margin-bottom:var(--sp-2);display:flex;align-items:center;gap:var(--sp-2)}
.status-badge{font-size:var(--fs-caption);font-weight:700;padding:var(--sp-1) var(--sp-2);border-radius:var(--r-pill);letter-spacing:.04em;flex-shrink:0}.sb-approved{background:var(--success-soft);color:var(--success)}.sb-attention{background:var(--warn-soft);color:var(--warn)}.sb-rejected,.sb-bad{background:var(--danger-soft);color:var(--danger)}.sb-manual{background:var(--info-soft);color:var(--info)}.sb-reviewing{background:var(--sky-canvas);color:var(--sky-blue)}
.btn-spinner{width:var(--sp-3);height:var(--sp-3);border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:spinIcon .7s linear infinite;display:inline-block}.bottom-pad{height:var(--sp-16)}.toast{position:fixed;bottom:var(--sp-5);left:50%;transform:translateX(-50%) translateY(var(--sp-5));background:var(--sky-navy);color:#fff;padding:var(--sp-3) var(--sp-5);border-radius:var(--r);font-size:var(--fs-xs);font-weight:600;opacity:0;transition:all var(--dur) var(--ease);z-index:var(--z-toast);white-space:nowrap;pointer-events:none}.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}.tipo-empty{text-align:center;padding:var(--sp-10) var(--sp-5);color:var(--mute)}.tipo-empty svg{opacity:.2;margin-bottom:var(--sp-3)}.tipo-empty p{font-size:var(--fs-sm)}
@media(max-width:720px){.tipo-selector{padding-inline:var(--sp-4)}.progress-card,.doc-section{margin-inline:var(--sp-4)}.progress-top{align-items:flex-start;flex-direction:column}}
</style>'''
ver = sub_once(ver, r"<style>.*?</style>", VER_CSS, "Verificador skin", re.S)

# Remove obsolete hidden app sidebar copy: shared chrome belongs to app-shell.js.
ver = sub_once(
    ver,
    r"\n<!-- shell-replaced-sidebar -->\n<div style=\"display:none\" hidden>.*?</div>\n\n<!-- HEADER -->",
    "\n<!-- HEADER -->",
    "Verificador hidden sidebar",
    re.S,
)

# Replace icon glyphs with compact text/SVG-neutral labels. This keeps every action
# and status readable without a second icon system or emoji dependency.
replacements = {
    '<div class="tipo-ico">🏠</div>': '<div class="tipo-ico" aria-hidden="true">AR</div>',
    '<div class="tipo-ico">🏛️</div>': '<div class="tipo-ico" aria-hidden="true">CV</div>',
    '✅ 0': 'OK 0', '⚠️ 0': 'Atención 0', '❌ 0': 'Rechazados 0', '⭕ 0': 'Pendientes 0',
    "ico: '👤'": "ico: 'PROP'", "ico: '🙋'": "ico: 'CLI'", "ico: '🤝'": "ico: 'AVAL'",
    "ico: '🏛️'": "ico: 'INM'", "ico: '🏷️'": "ico: 'VEND'", "ico: '📋'": "ico: 'DOC'",
    "pending:   { ico: '⭕'": "pending:   { ico: '—'",
    "reviewing: { ico: '⏳'": "reviewing: { ico: '…'",
    "approved:  { ico: '✅'": "approved:  { ico: 'OK'",
    "attention: { ico: '⚠️'": "attention: { ico: '!'",
    "rejected:  { ico: '❌'": "rejected:  { ico: 'NO'",
    "manual:    { ico: '☑️'": "manual:    { ico: 'OK'",
    "`✅ ${ok}`": "`OK ${ok}`", "`⚠️ ${warn}`": "`Atención ${warn}`",
    "`❌ ${bad}`": "`Rechazados ${bad}`", "`⭕ ${pend}`": "`Pendientes ${pend}`",
    "'🔍 Revisado el '": "'Revisado el '",
    '📌 <strong>Qué necesitas:</strong>': '<strong>Qué necesitas:</strong>',
    '✅ <strong>Requisitos clave:</strong>': '<strong>Requisitos clave:</strong>',
    "${estado.has_file ? '📄' : '📎'}": "${estado.has_file ? 'DOC' : 'SUBIR'}",
    '<span id="ai-btn-inner-${doc.id}">✨ Analizar con IA</span>': '<span id="ai-btn-inner-${doc.id}">Analizar con IA</span>',
    '>☑️ Marcar como revisado</button>': '>Marcar como revisado</button>',
    '>↺ Reiniciar</button>': '>Reiniciar</button>',
    "textContent = '📄'": "textContent = 'DOC'",
    "ico.textContent = '⏳'": "ico.textContent = '…'",
    "inner.textContent = '✨ Analizar con IA'": "inner.textContent = 'Analizar con IA'",
    "'⚠️ El servidor no pudo analizar": "'El servidor no pudo analizar",
    '1. 🔍 IDENTIFICACIÓN:': '1. IDENTIFICACIÓN:',
    '2. 📋 DATOS EXTRAÍDOS:': '2. DATOS EXTRAÍDOS:',
    '3. ✅ VALIDEZ FORMAL:': '3. VALIDEZ FORMAL:',
    '4. ⚠️ PROBLEMAS DETECTADOS:': '4. PROBLEMAS DETECTADOS:',
    '5. 📌 RECOMENDACIONES:': '5. RECOMENDACIONES:',
}
for old, new in replacements.items():
    if old not in ver:
        raise RuntimeError(f"Verificador expected icon pattern missing: {old!r}")
    ver = ver.replace(old, new)

# No emoji-range code points may remain in this product surface.
emoji_re = re.compile('[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]')
left = emoji_re.findall(ver)
if left:
    raise RuntimeError(f"Verificador still contains emoji/icon glyphs: {sorted(set(left))}")
write("verificador.html", ver)

print("Canon outlier transform applied: isr.html, bandeja.html, legal.html, verificador.html")
