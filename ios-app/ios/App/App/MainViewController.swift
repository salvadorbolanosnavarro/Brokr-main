import Capacitor
import UIKit

/// Broquer se debe sentir como una app nativa, no como una página web abierta
/// en un navegador — nada de rebote elástico al llegar al borde del scroll,
/// ni arrastres que revelen un hueco blanco a los lados o abajo.
///
/// El CSS de brokr-theme.css (`overscroll-behavior: none`, `touch-action:
/// pan-y`) ya controla el "scroll chaining" DENTRO del DOM, pero el
/// WKWebView de Capacitor trae su propio UIScrollView nativo por debajo, y
/// ese sigue rebotando aunque el CSS lo pida — eso solo se apaga aquí, a
/// nivel nativo. Sin esto, cualquier pantalla puede "jalarse" verticalmente
/// más allá de su contenido real, o mostrar un tirón lateral fantasma al
/// arrastrar cerca del borde.
class MainViewController: CAPBridgeViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        guard let scrollView = webView?.scrollView else { return }
        scrollView.bounces = false
        scrollView.alwaysBounceVertical = false
        scrollView.alwaysBounceHorizontal = false
    }
}
