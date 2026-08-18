from pathlib import Path

path = Path("brokr-theme.css")
text = path.read_text(encoding="utf-8")
marker = "/* BROQUER-PREMIUM-PROPERTIES-CONTACTS */"
if marker in text:
    print("premium pass already present")
    raise SystemExit(0)

css = r'''

/* BROQUER-PREMIUM-PROPERTIES-CONTACTS
   Product-composition pass: Propiedades + Contactos.
   Scoped by data-app; no business logic or markup ownership changes. */

/* ── Propiedades: operational real-estate catalog ─────────── */
body[data-app="propiedades"] .props-head {
  padding: var(--sp-7) var(--pad-x) var(--sp-5);
  background: var(--paper);
  border-bottom: 0;
}
body[data-app="propiedades"] .props-head__top {
  align-items: center;
  margin-bottom: var(--sp-5);
}
body[data-app="propiedades"] .props-head__eyebrow {
  color: var(--sky-blue);
  font-weight: 700;
  letter-spacing: 0.04em;
}
body[data-app="propiedades"] .props-head__title h1 {
  font-size: var(--fs-h1);
  line-height: var(--lh-h1);
}
body[data-app="propiedades"] .props-head__count {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 var(--sp-3);
  margin-left: var(--sp-2);
  border-radius: var(--r-pill);
  background: var(--paper-2);
  color: var(--mute);
}
body[data-app="propiedades"] .btn-new-prop,
body[data-app="propiedades"] .btn-import-eb {
  height: var(--h);
  border-radius: var(--r-sm);
  font-weight: 700;
}
body[data-app="propiedades"] .btn-new-prop {
  background: var(--sky-blue);
  box-shadow: var(--shadow-xs);
}
body[data-app="propiedades"] .btn-new-prop:hover { background: var(--sky-blue-press); }
body[data-app="propiedades"] .btn-import-eb {
  background: var(--bone);
  border: 1px solid var(--line-2);
  margin-right: 0;
}
body[data-app="propiedades"] .props-toolbar {
  gap: var(--sp-2);
  padding: var(--sp-2);
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
}
body[data-app="propiedades"] .props-search-wrap,
body[data-app="propiedades"] .props-toolbar select,
body[data-app="propiedades"] .props-filter-est-btn,
body[data-app="propiedades"] .props-price-wrap {
  height: var(--h);
  border-radius: var(--r);
  border-color: var(--line-2);
  background-color: var(--bone);
  box-shadow: none;
}
body[data-app="propiedades"] .props-search-wrap { min-width: 300px; }
body[data-app="propiedades"] .props-search-wrap:focus-within,
body[data-app="propiedades"] .props-price-wrap:focus-within {
  border-color: var(--sky-blue);
  box-shadow: var(--focus);
}
body[data-app="propiedades"] .props-grid {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: var(--sp-5) var(--pad-x) var(--sp-12);
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--sp-5);
}
body[data-app="propiedades"] .prop-card {
  border-color: var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-xs);
  background: var(--bone);
}
body[data-app="propiedades"] .prop-card:hover {
  transform: translateY(-1px);
  border-color: var(--line-3);
  box-shadow: var(--shadow);
}
body[data-app="propiedades"] .prop-card-img { aspect-ratio: 16 / 10; }
body[data-app="propiedades"] .prop-card-img img {
  filter: saturate(.92) contrast(1.02);
}
body[data-app="propiedades"] .prop-card:hover .prop-card-img img { transform: scale(1.015); }
body[data-app="propiedades"] .prop-card-body { padding: var(--sp-5); }
body[data-app="propiedades"] .prop-card-loc {
  margin-bottom: var(--sp-2);
  color: var(--mute);
  font-weight: 600;
}
body[data-app="propiedades"] .prop-card-title {
  min-height: 0;
  margin-bottom: var(--sp-3);
  font-size: var(--fs-h5);
  line-height: var(--lh-snug);
}
body[data-app="propiedades"] .prop-card-price-row { margin-bottom: var(--sp-4); }
body[data-app="propiedades"] .prop-card-price {
  font-size: var(--fs-h2);
  font-weight: 800;
}
body[data-app="propiedades"] .prop-card-specs {
  gap: var(--sp-4);
  padding-top: var(--sp-3);
  color: var(--mute);
}
body[data-app="propiedades"] .prop-card-actions {
  gap: var(--sp-1);
  padding: var(--sp-2) var(--sp-3) var(--sp-3);
  background: var(--paper-2);
  border-top-color: var(--line);
}
body[data-app="propiedades"] .prop-act-btn {
  height: var(--h-sm);
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  font-weight: 600;
}
body[data-app="propiedades"] .prop-act-btn:hover {
  background: var(--bone);
  box-shadow: var(--shadow-xs);
}
body[data-app="propiedades"] .props-empty {
  margin: var(--sp-6) auto;
  max-width: 620px;
  padding: var(--sp-12) var(--sp-7);
  border: 1px dashed var(--line-2);
  border-radius: var(--r-xl);
  background: var(--paper-2);
}

/* ── Contactos: dense CRM list, not a stack of floating cards ─ */
body[data-app="contactos"] .page-head {
  position: relative;
  top: auto;
  z-index: auto;
  padding: var(--sp-7) var(--pad-x) 0;
  border-bottom: 0;
  background: var(--paper);
}
body[data-app="contactos"] .page-head__crumbs {
  margin-bottom: var(--sp-2);
  color: var(--sky-blue);
  font-weight: 700;
}
body[data-app="contactos"] .page-head__row { margin-bottom: var(--sp-5); }
body[data-app="contactos"] .page-head h1 {
  font-size: var(--fs-h1);
  line-height: var(--lh-h1);
}
body[data-app="contactos"] .page-head__count {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  padding: 0 var(--sp-3);
  background: var(--paper-2);
  border: 0;
  letter-spacing: 0;
}
body[data-app="contactos"] .head-search {
  width: 100%;
  max-width: none;
  height: var(--h);
  margin-bottom: var(--sp-2);
  border-radius: var(--r);
  border-color: var(--line-2);
  background: var(--paper-2);
}
body[data-app="contactos"] .head-search:focus-within {
  background: var(--bone);
  border-color: var(--sky-blue);
  box-shadow: var(--focus);
}
body[data-app="contactos"] .filters-row {
  gap: var(--sp-2);
  padding: var(--sp-2) 0;
  margin-bottom: var(--sp-2);
}
body[data-app="contactos"] .filtro-select,
body[data-app="contactos"] .contacts-select-all {
  height: var(--h-sm);
  border-radius: var(--r-sm);
  background-color: var(--bone);
  border-color: var(--line-2);
  font-weight: 600;
}
body[data-app="contactos"] .tabs {
  gap: var(--sp-6);
  border-bottom-color: var(--line-2);
}
body[data-app="contactos"] .ftab {
  padding: var(--sp-3) 0;
  font-weight: 600;
}
body[data-app="contactos"] .ftab.active {
  color: var(--ink);
  border-bottom-color: var(--sky-blue);
  font-weight: 700;
}
body[data-app="contactos"] .list {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: var(--sp-4) var(--pad-x) var(--sp-20);
}
body[data-app="contactos"] .contact-card {
  min-height: 72px;
  margin-bottom: 0;
  padding: var(--sp-3) var(--sp-2);
  border: 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  background: var(--paper);
  transform: none;
}
body[data-app="contactos"] .contact-card:first-child {
  border-top: 1px solid var(--line);
}
body[data-app="contactos"] .contact-card:hover {
  transform: none;
  background: var(--paper-2);
  border-color: var(--line);
}
body[data-app="contactos"] .contact-card.is-selected {
  background: var(--sky-canvas);
  border-color: var(--line);
}
body[data-app="contactos"] .avatar {
  width: 40px;
  height: 40px;
  font-weight: 700;
}
body[data-app="contactos"] .contact-name {
  font-weight: 650;
  font-size: var(--fs-sm);
}
body[data-app="contactos"] .contact-meta { margin-top: var(--sp-1); }
body[data-app="contactos"] .role-badge,
body[data-app="contactos"] .tag-chip {
  padding: 2px var(--sp-2);
  border-radius: var(--r-sm);
}
body[data-app="contactos"] .quick-acts { gap: var(--sp-1); }
body[data-app="contactos"] .qa {
  width: var(--h-sm);
  height: var(--h-sm);
  border-radius: var(--r-sm);
  border-color: transparent;
  background: transparent;
}
body[data-app="contactos"] .qa:hover {
  border-color: var(--line-2);
  background: var(--bone);
  box-shadow: var(--shadow-xs);
  color: var(--sky-blue);
}
body[data-app="contactos"] .empty {
  margin: var(--sp-6) auto;
  max-width: 620px;
  padding: var(--sp-12) var(--sp-7);
  border: 1px dashed var(--line-2);
  border-radius: var(--r-xl);
  background: var(--paper-2);
}

@media (max-width: 720px) {
  body[data-app="propiedades"] .props-head,
  body[data-app="contactos"] .page-head { padding-left: var(--sp-4); padding-right: var(--sp-4); }
  body[data-app="propiedades"] .props-toolbar { padding: var(--sp-2); }
  body[data-app="propiedades"] .props-search-wrap { min-width: 100%; }
  body[data-app="propiedades"] .props-grid { padding: var(--sp-4); grid-template-columns: 1fr; }
  body[data-app="propiedades"] .prop-card-img { aspect-ratio: 16 / 9; }
  body[data-app="contactos"] .list { padding: var(--sp-2) var(--sp-4) var(--sp-20); }
  body[data-app="contactos"] .contact-card {
    margin-bottom: var(--sp-2);
    padding: var(--sp-4);
    border: 1px solid var(--line-2);
    border-radius: var(--r-lg);
    background: var(--bone);
  }
  body[data-app="contactos"] .contact-card:first-child { border-top: 1px solid var(--line-2); }
}
'''

path.write_text(text.rstrip() + css + "\n", encoding="utf-8")
print("applied Properties + Contacts premium pass")
