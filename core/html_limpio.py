"""Limpia el HTML del editor de páginas del sitio (lista blanca).

Deja formato básico (párrafos, títulos, listas, negritas, ligas, imágenes,
tablas simples) y quita todo lo demás: scripts, estilos, eventos (onclick…),
iframes y ligas javascript:. El texto siempre se conserva.
"""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser

PERMITIDAS = {"p", "br", "strong", "b", "em", "i", "u", "h2", "h3", "h4", "ul", "ol", "li", "a", "blockquote",
              "img", "hr", "table", "thead", "tbody", "tr", "td", "th", "span", "div"}
VACIAS = {"br", "img", "hr"}
ATRIBUTOS = {"a": {"href", "target", "rel"}, "img": {"src", "alt"}, "td": {"colspan"}, "th": {"colspan"}}
DESCARTAR_CONTENIDO = {"script", "style", "iframe", "object", "embed", "noscript", "template"}


def _url_ok(url: str, img: bool = False) -> bool:
    u = (url or "").strip().lower()
    if img:
        return u.startswith("https://")
    return u.startswith(("https://", "http://", "mailto:", "tel:", "/", "#"))


class _Limpiador(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.pila = []
        self.saltar = 0

    def handle_starttag(self, tag, attrs):
        if tag in DESCARTAR_CONTENIDO:
            self.saltar += 1
            return
        if self.saltar or tag not in PERMITIDAS:
            return
        partes = [tag]
        for k, v in attrs:
            if k not in ATRIBUTOS.get(tag, set()) or v is None:
                continue
            if k in ("href", "src") and not _url_ok(v, img=(k == "src")):
                continue
            if k == "colspan" and not v.isdigit():
                continue
            partes.append(f'{k}="{escape(v, quote=True)}"')
        if tag == "a":
            partes += ['rel="noopener nofollow"'] if not any(p.startswith("rel=") for p in partes) else []
        self.out.append("<" + " ".join(partes) + ">")
        if tag not in VACIAS:
            self.pila.append(tag)

    def handle_endtag(self, tag):
        if tag in DESCARTAR_CONTENIDO:
            self.saltar = max(0, self.saltar - 1)
            return
        if self.saltar or tag not in PERMITIDAS or tag in VACIAS or tag not in self.pila:
            return
        while self.pila:
            t = self.pila.pop()
            self.out.append(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if not self.saltar:
            self.out.append(escape(data, quote=False))


def limpiar_html(html: str, limite: int = 200_000) -> str:
    p = _Limpiador()
    p.feed((html or "")[:limite])
    p.close()
    while p.pila:
        p.out.append(f"</{p.pila.pop()}>")
    return "".join(p.out)
