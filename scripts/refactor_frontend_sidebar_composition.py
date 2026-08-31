from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "sidebar-composition-normalization"

STYLES = {
    "propiedades.html": r'''
/* Sidebar composition normalization: shared product skeleton only. */
.props-head {
  max-width: var(--page-max, 1180px) !important;
  margin: 0 auto !important;
  padding: 28px var(--pad-x, 36px) 18px !important;
  border-bottom: 1px solid var(--line) !important;
}
.props-head__title h1 {
  font-size: 30px !important;
  line-height: 1.05 !important;
  letter-spacing: -0.02em !important;
}
@media (max-width:720px) {
  .props-head { padding:16px var(--pad-x,16px) 14px !important; }
  .props-head__title h1 { font-size:24px !important; }
}
''',
    "contactos.html": r'''
/* Sidebar composition normalization: shared product skeleton only. */
.page-head {
  position: static !important;
  top: auto !important;
  max-width: var(--page-max, 1180px) !important;
  margin: 0 auto !important;
  padding: 28px var(--pad-x, 36px) 0 !important;
}
.page-head h1 {
  font-size: 30px !important;
  line-height: 1.05 !important;
  letter-spacing: -0.02em !important;
}
.head-search { max-width:none !important; }
.list { max-width:var(--page-max,1180px) !important; margin:0 auto !important; }
@media (max-width:720px) {
  .page-head { padding:16px var(--pad-x,16px) 0 !important; }
  .page-head h1 { font-size:24px !important; }
}
''',
    "tareas.html": r'''
/* Sidebar composition normalization: shared product skeleton only. */
.tk-head {
  max-width: var(--page-max, 1180px) !important;
  margin: 0 auto !important;
  padding: 28px var(--pad-x, 36px) 0 !important;
}
.tk-head__title h1 {
  font-size:30px !important;
  line-height:1.05 !important;
  letter-spacing:-0.02em !important;
}
.tk-body { margin:0 auto !important; }
@media (max-width:720px) {
  .tk-head { padding:16px var(--pad-x,16px) 0 !important; }
  .tk-head__title h1 { font-size:24px !important; }
}
''',
    "leads.html": r'''
/* Sidebar composition normalization: shared product skeleton only. */
.page-head {
  position: static !important;
  top: auto !important;
  max-width: var(--page-max, 1180px) !important;
  margin: 0 auto !important;
  padding: 28px var(--pad-x, 36px) 0 !important;
}
.page-head h1 {
  font-size:30px !important;
  line-height:1.05 !important;
  letter-spacing:-0.02em !important;
}
.head-search { max-width:none !important; }
.list { max-width:var(--page-max,1180px) !important; margin:0 auto !important; }
@media (max-width:720px) {
  .page-head { padding:16px var(--pad-x,16px) 0 !important; }
  .page-head h1 { font-size:24px !important; }
}
''',
    "avm.html": r'''
/* Sidebar composition normalization: remove standalone navy mini-app chrome. */
.avm-header {
  background:var(--paper) !important;
  max-width:var(--page-max,1180px) !important;
  margin:0 auto !important;
  padding:28px var(--pad-x,36px) 10px !important;
  overflow:visible !important;
}
.avm-header::before { display:none !important; }
.avm-title {
  color:var(--ink) !important;
  font-size:30px !important;
  line-height:1.05 !important;
  letter-spacing:-0.02em !important;
}
.avm-sub { color:var(--mute) !important; opacity:1 !important; }
.avm-tabs {
  background:var(--paper) !important;
  border-bottom:1px solid var(--line) !important;
  max-width:var(--page-max,1180px) !important;
  margin:0 auto !important;
  padding:0 var(--pad-x,36px) !important;
}
.avm-tab {
  color:var(--mute) !important;
  border-bottom-color:transparent !important;
}
.avm-tab.active {
  color:var(--ink) !important;
  border-bottom-color:var(--sky-blue) !important;
}
.avm-body {
  max-width:var(--page-max,1180px) !important;
  margin:0 auto !important;
  padding:24px var(--pad-x,36px) 100px !important;
}
.btn-primary { background:var(--sky-blue) !important; }
@media (max-width:720px) {
  .avm-header { padding:16px var(--pad-x,16px) 8px !important; }
  .avm-title { font-size:24px !important; }
  .avm-tabs { padding:0 var(--pad-x,16px) !important; }
  .avm-body { padding:16px var(--pad-x,16px) 100px !important; }
}
''',
}


def ensure_theme_link(text: str, name: str) -> str:
    if name != "avm.html" or 'href="brokr-theme.css"' in text:
        return text
    needle = "</title>"
    if needle not in text:
        raise RuntimeError(f"{name}: no </title> anchor for deterministic theme insertion")
    return text.replace(needle, needle + '\n  <link rel="stylesheet" href="brokr-theme.css"/>', 1)


def apply(name: str, css: str) -> bool:
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    text = ensure_theme_link(text, name)
    block = f'\n<style id="{MARKER}">\n{css.strip()}\n</style>\n'
    start = text.find(f'<style id="{MARKER}">')
    if start >= 0:
        end = text.find("</style>", start)
        if end < 0:
            raise RuntimeError(f"{name}: malformed existing normalization block")
        end += len("</style>")
        new = text[:start] + block.strip() + text[end:]
    else:
        anchor = "</head>"
        if anchor not in text:
            raise RuntimeError(f"{name}: no </head> anchor")
        new = text.replace(anchor, block + anchor, 1)
    if new == path.read_text(encoding="utf-8"):
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main() -> None:
    changed = [name for name, css in STYLES.items() if apply(name, css)]
    print("changed:", ", ".join(changed) if changed else "none")


if __name__ == "__main__":
    main()
