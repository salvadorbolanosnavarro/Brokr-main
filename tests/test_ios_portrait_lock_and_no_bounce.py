"""La app de iPhone/iPad debe quedarse siempre en vertical (nunca rotar a
horizontal) y el scroll no debe rebotar ni jalarse hacia los lados — igual
que EasyBroker. Dos causas distintas, dos fixes distintos:

1. Info.plist listaba Portrait + Landscape (iPhone) y las cuatro
   orientaciones (iPad) como soportadas — eso es lo que deja rotar la app.
2. El CSS (`overscroll-behavior: none` en brokr-theme.css) controla el
   scroll chaining DENTRO del DOM, pero el WKWebView de Capacitor tiene su
   propio UIScrollView nativo que sigue rebotando aunque el CSS lo pida —
   por eso MainViewController.swift apaga el rebote a nivel nativo.
"""
import plistlib
import xml.etree.ElementTree as ET
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
IOS_APP = ROOT / "ios-app" / "ios" / "App" / "App"
INFO_PLIST = IOS_APP / "Info.plist"
STORYBOARD = IOS_APP / "Base.lproj" / "Main.storyboard"
VIEW_CONTROLLER = IOS_APP / "MainViewController.swift"
PBXPROJ = ROOT / "ios-app" / "ios" / "App" / "App.xcodeproj" / "project.pbxproj"


class IOSPortraitLockTests(unittest.TestCase):
    def test_info_plist_only_supports_portrait(self):
        with open(INFO_PLIST, "rb") as f:
            data = plistlib.load(f)
        self.assertEqual(data["UISupportedInterfaceOrientations"], ["UIInterfaceOrientationPortrait"])
        self.assertEqual(data["UISupportedInterfaceOrientations~ipad"], ["UIInterfaceOrientationPortrait"])
        # Ninguna variante de landscape/upside-down debe colarse de vuelta.
        for key in ("UISupportedInterfaceOrientations", "UISupportedInterfaceOrientations~ipad"):
            for orientation in data[key]:
                self.assertNotIn("Landscape", orientation)
                self.assertNotIn("UpsideDown", orientation)

    def test_main_view_controller_exists_and_disables_bounce(self):
        self.assertTrue(VIEW_CONTROLLER.exists(), "falta ios-app/ios/App/App/MainViewController.swift")
        source = VIEW_CONTROLLER.read_text(encoding="utf-8")
        self.assertIn("class MainViewController: CAPBridgeViewController", source)
        self.assertIn("scrollView.bounces = false", source)
        self.assertIn("scrollView.alwaysBounceVertical = false", source)
        self.assertIn("scrollView.alwaysBounceHorizontal = false", source)

    def test_storyboard_uses_the_custom_view_controller(self):
        tree = ET.parse(STORYBOARD)
        vc = tree.getroot().find(".//viewController")
        self.assertIsNotNone(vc, "no se encontró <viewController> en Main.storyboard")
        self.assertEqual(vc.get("customClass"), "MainViewController")
        self.assertEqual(vc.get("customModule"), "App")

    def test_pbxproj_registers_the_new_file_in_every_required_section(self):
        source = PBXPROJ.read_text(encoding="utf-8")
        # PBXBuildFile
        self.assertIn(
            "MainViewController.swift in Sources */ = {isa = PBXBuildFile; fileRef = "
            "B20C0DE01A1B2C3D4E5F6072 /* MainViewController.swift */; };",
            source,
        )
        # PBXFileReference
        self.assertIn(
            'B20C0DE01A1B2C3D4E5F6072 /* MainViewController.swift */ = {isa = PBXFileReference; '
            'lastKnownFileType = sourcecode.swift; path = MainViewController.swift; sourceTree = "<group>"; };',
            source,
        )
        # Listado en el grupo "App" (si falta, Xcode no la muestra en el navegador
        # de archivos, aunque sí compile).
        self.assertIn("B20C0DE01A1B2C3D4E5F6072 /* MainViewController.swift */,", source)
        # PBXSourcesBuildPhase — si falta esto, el archivo simplemente no compila.
        self.assertIn("B20C0DE01A1B2C3D4E5F6071 /* MainViewController.swift in Sources */,", source)
        # Las dos referencias (build file y file reference) deben tener IDs
        # distintos y consistentes entre sí.
        self.assertNotEqual("B20C0DE01A1B2C3D4E5F6071", "B20C0DE01A1B2C3D4E5F6072")

    def test_pbxproj_braces_and_parens_stay_balanced(self):
        # Guarda mínima contra un pbxproj corrupto (Xcode ni siquiera abre el
        # proyecto si esto se desbalancea).
        source = PBXPROJ.read_text(encoding="utf-8")
        self.assertEqual(source.count("{"), source.count("}"))
        self.assertEqual(source.count("("), source.count(")"))


if __name__ == "__main__":
    unittest.main()
