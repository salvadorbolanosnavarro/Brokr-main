from pathlib import Path

MARKER = "/* CANON-COMPOSITION-NORMALIZATION */"

OVERRIDES = {
    "estadisticas.html": r'''
/* CANON-COMPOSITION-NORMALIZATION */
.es-hero {
  background: var(--paper);
  color: var(--ink);
  padding: 28px 36px 18px;
  border-bottom: 1px solid var(--line);
}
@media (max-width: 720px) { .es-hero { padding: 20px 16px 16px; } }
.es-hero h1 { color: var(--ink); }
.es-hero__sub { color: var(--mute); opacity: 1; }
.es-hero__count {
  color: var(--ink-2);
  background: var(--paper-2);
  border: 1px solid var(--line-2);
}
.es-seg {
  background: var(--paper-2);
  border: 1px solid var(--line-2);
  margin-top: 16px;
}
.es-seg button { color: var(--mute); opacity: 1; }
.es-seg button:hover { color: var(--ink); }
.es-seg button.is-active {
  background: var(--bone);
  color: var(--ink);
  box-shadow: var(--shadow-xs);
}
.es-seg button:focus-visible { box-shadow: var(--focus); }
.es-nav {
  position: sticky;
  top: 0;
  margin: 0 36px;
  padding-top: 10px;
  background: var(--paper);
}
@media (max-width: 720px) { .es-nav { margin: 0 12px; } }
.es-nav__card {
  box-shadow: none;
  border: 0;
  border-bottom: 1px solid var(--line-2);
  border-radius: 0;
  padding: 0;
  max-width: calc(var(--page-max) - 72px);
}
.tabs { gap: var(--sp-5); }
.ftab {
  border-radius: 0;
  padding: 12px 0 10px;
  border-bottom: 2px solid transparent;
}
.ftab:hover { background: transparent; color: var(--ink); }
.ftab.active {
  background: transparent;
  color: var(--ink);
  border-bottom-color: var(--sky-blue);
  font-weight: 700;
}
.es-scroll { padding-top: 24px; }
''',
    "avm.html": r'''
/* CANON-COMPOSITION-NORMALIZATION */
.avm-header {
  background: var(--paper);
  padding: calc(var(--safe-top) + 20px) 24px 16px;
  border-bottom: 1px solid var(--line);
  overflow: visible;
}
.avm-header::before { display: none; }
.avm-title {
  color: var(--ink);
  letter-spacing: -0.025em;
  font-size: var(--fs-h2);
}
.avm-sub {
  color: var(--mute);
  letter-spacing: 0;
  margin-top: var(--sp-1);
}
.avm-tabs {
  background: var(--paper);
  border-bottom: 1px solid var(--line-2);
  padding: 0 24px;
  gap: var(--sp-5);
}
.avm-tab {
  flex: 0 0 auto;
  padding: 12px 0 10px;
  color: var(--mute);
  border-bottom: 2px solid transparent;
}
.avm-tab:hover { color: var(--ink); }
.avm-tab.active {
  color: var(--ink);
  border-bottom-color: var(--sky-blue);
  font-weight: 700;
}
.avm-body {
  padding: 24px 24px 80px;
  max-width: var(--form-max);
  margin: 0 auto;
}
@media (max-width: 720px) {
  .avm-header { padding-left: 16px; padding-right: 16px; }
  .avm-tabs { padding: 0 16px; gap: var(--sp-4); }
  .avm-body { padding: 16px 16px 80px; }
}
''',
}


def inject(path: Path, css: str) -> None:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return
    idx = text.find("</style>")
    if idx < 0:
        raise SystemExit(f"{path}: no </style> found")
    text = text[:idx] + css + "\n" + text[idx:]
    path.write_text(text, encoding="utf-8")


for filename, css in OVERRIDES.items():
    inject(Path(filename), css)

print("normalized:", ", ".join(OVERRIDES))
