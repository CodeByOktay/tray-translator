"""
Adim 3 - Ctrl+Alt+T global kisayolu + sistem tepsisi + tek ornek korumasi.

Onkosul:
    pip install pynput
    window.py, providers.py ve engine.py ayni klasorde olmali.

Calistirmak icin:
    python main.py

Uygulama sistem tepsisine yerlesir ve arka planda calisir.
Ctrl+Alt+T ile pencere acilir, panodaki metin (yeniyse) kaynak
alanina yazilir. Pencereyi kapatmak uygulamayi kapatmaz;
tamamen cikmak icin tepsi menusundeki Cikis kullanilir.

Uygulama ikinci kez calistirilirsa yeni bir ornek acilmaz:
var olan orneğin penceresi one getirilir.
"""

import logging
import sys

import logsetup

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from pynput import keyboard

from window import TranslatorWindow

HOTKEY = "<alt>+t"
HOTKEY_LABEL = "Alt+T"

# Yerel soketin adi. Bilgisayarda benzersiz olmali; baska bir
# programin ayni adi kullanma ihtimali dusuk olsun diye uzun tuttuk.
SERVER_NAME = "ceviri-agenti-tek-ornek-v1"


class HotkeyBridge(QObject):
    """Kisayol dinleyicisi ile arayuz arasinda kopru.

    pynput dinleyicisi kendi is parcaciginda calisir. Qt'de arayuz
    nesnelerine baska bir is parcacigindan dokunmak yasaktir; program
    rastgele cokebilir. Bu yuzden dinleyici pencereyi dogrudan acmaz,
    sadece sinyal yayinlar. Sinyali ana is parcacigi alir ve pencereyi
    orada acar.
    """

    triggered = Signal()


class TrayTranslatorWindow(TranslatorWindow):
    """Adim 2'deki pencereye tepsi davranisi ekler.

    Kalitim kullaniyoruz: window.py'ye hic dokunmadan davranis
    degistiriyoruz. Model kutusu, is parcacigi ve kopyalama oldugu
    gibi devraliniyor.
    """

    def __init__(self) -> None:
        super().__init__()

    def closeEvent(self, event) -> None:
        """Pencere kapatilinca uygulamadan cikma, sadece gizle.

        Suren ceviri varsa iptal edilir: sonucunu goremeyecegimiz bir
        istegin arka planda calismaya devam etmesinin anlami yok.
        """
        self._cancel_translation()
        event.ignore()
        self.hide()

    def toggle(self) -> None:
        """Kisayol davranisi: pencere acikken gizle, kapaliyken ac.

        hide() kullaniyoruz, close() degil. Kisayol kucultme gibi
        davranmali: suren ceviri iptal edilmemeli.
        """
        if self.isVisible():
            self.hide()
        else:
            self.show_window()


    def show_window(self) -> None:
      """Pencereyi ac. Kaynak alani her zaman bos baslar.

      Panodan otomatik yapistirma yok; kullanici kendisi yapistirir.
      Ceviri alanina dokunmuyoruz: bir onceki sonuc, yeni bir ceviri
      baslayana kadar ekranda kalir.
      """
      self.input_box.clear()
      self.show()
      self.raise_()
      self.activateWindow()
      self.input_box.setFocus()


def another_instance_is_running() -> bool:
    """Baska bir ornek calisiyor mu diye bakar.

    Yerel sokete baglanmayi dener. Baglanabiliyorsa karsida dinleyen
    bir ornek var demektir; ona "pencereyi ac" mesajini gonderip
    True doner. Baglanamiyorsa ilk ornek biziz.

    Kilit dosyasi yerine soket kullanmanin iki avantaji var:
    program coktugunde soket sistemle birlikte kapanir (bayat kilit
    dosyasi kalmaz) ve ikinci ornek bosuna kapanmak yerine var olan
    pencereyi one getirebilir.
    """
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(300):
        return False

    socket.write(b"show")
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


def build_icon() -> QIcon:

    """Tepsi ikonunu kod icinde cizer.

    Ayri bir .ico dosyasi tasimamak icin. Kendi ikonunu kullanmak
    istersen bu fonksiyonu QIcon("ikon.ico") ile degistir.
    """
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#3b82f6"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)

    painter.setPen(QColor("#ffffff"))
    font = painter.font()
    font.setPointSize(24)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "TR")
    painter.end()

    return QIcon(pixmap)


def main() -> None:
    app = QApplication(sys.argv)

    # ONCE tek ornek kontrolu: gereksiz kurulum yapmadan cikalim
    if another_instance_is_running():
        sys.exit(0)

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        # Tek ornek korumasi kurulamadi. Uygulama yine de calisir,
        # ama ikinci bir ornek acilabilir.
        logging.warning(
            "Tek ornek korumasi kurulamadi: %s", server.errorString()
        )
    # Son pencere kapandiginda uygulamadan cikma. Bu satir olmazsa
    # pencereyi gizledigin anda uygulama tamamen kapanir.
    app.setQuitOnLastWindowClosed(False)

    window = TrayTranslatorWindow()

    def on_second_instance() -> None:
        """Ikinci ornek baglandiginda pencereyi one getir."""
        connection = server.nextPendingConnection()
        if connection is not None:
            connection.disconnectFromServer()
        window.show_window()

    server.newConnection.connect(on_second_instance)

    bridge = HotkeyBridge()
    bridge.triggered.connect(window.toggle)

    listener = keyboard.GlobalHotKeys({HOTKEY: bridge.triggered.emit})
    listener.daemon = True
    listener.start()
    # Program nasil kapanirsa kapansin dinleyici ve sunucu temizlensin
    app.aboutToQuit.connect(listener.stop)
    app.aboutToQuit.connect(server.close)

    tray = QSystemTrayIcon(build_icon(), parent=app)
    tray.setToolTip(f"Ceviri Agenti  ({HOTKEY_LABEL})")

    menu = QMenu()

    open_action = QAction("Pencereyi ac", menu)
    open_action.triggered.connect(window.show_window)
    menu.addAction(open_action)

    menu.addSeparator()

    quit_action = QAction("Cikis", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()

    def on_tray_activated(reason) -> None:
        """Tepsi ikonuna cift tiklayinca pencereyi ac."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            window.show_window()

    tray.activated.connect(on_tray_activated)

    tray.showMessage(
        "Ceviri Agenti calisiyor",
        f"{HOTKEY_LABEL} ile pencereyi acabilirsiniz.",
        QSystemTrayIcon.MessageIcon.Information,
        3000,
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    logsetup.install()
    main()
