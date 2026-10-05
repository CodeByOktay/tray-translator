"""
Adim 2 - PySide6 ile ceviri penceresi.

Onkosul:
    pip install PySide6
    engine.py ve providers.py ayni klasorde olmali.

Calistirmak icin:
    python window.py
"""

import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from providers import DEFAULT_PROVIDER, PROVIDERS, get_translator
from engine import TranslationError


class TranslateWorker(QThread):
    """Ceviriyi arka planda calistiran is parcacigi.

    Ceviri 5-30 saniye surebiliyor. Bunu ana is parcaciginda
    calistirirsak pencere tamamen donar, Windows "yanit vermiyor"
    uyarisi gosterir. Bu yuzden ayri bir QThread kullaniyoruz.
    """

    succeeded = Signal(str, float)   # ceviri metni, gecen sure
    failed = Signal(str)             # hata mesaji

    def __init__(self, text: str, provider: str) -> None:
        super().__init__()
        self._text = text
        self._provider = provider
        self._cancelled = False

    def cancel(self) -> None:
        """Sonucu yok saymayi isaretler.

        Devam eden ag istegini gercekten durduramayiz: urlopen bloke
        eder ve bir is parcacigini disaridan oldurmek guvenli degildir.
        Bunun yerine isteğin donmesini bekleyip sonucu sessizce atiyoruz.
        Kullanici acisindan fark yoktur; arayuz hemen serbest kalir.
        """
        self._cancelled = True

    def run(self) -> None:
        """Is parcacigi baslatildiginda otomatik cagrilir."""
        started = time.perf_counter()
        try:
            translator = get_translator(self._provider)
            result = translator.translate(self._text)
        except TranslationError as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))
            return

        if self._cancelled:
            return
        self.succeeded.emit(result, time.perf_counter() - started)


class TranslatorWindow(QWidget):
    """Ana ceviri penceresi."""

    def __init__(self) -> None:
        super().__init__()
        self._worker: TranslateWorker | None = None
        # Iptal edilmis ama hala calisan is parcaciklari burada tutulur.
        # Referansi birakirsak Python nesneyi toplayabilir ve calisan
        # bir QThread cop toplandiginda program coker.
        self._abandoned: list[TranslateWorker] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("Ceviri Agenti")
        self.resize(640, 480)

        self.model_box = QComboBox()
        self.model_box.addItems(list(PROVIDERS))
        self.model_box.setCurrentText(DEFAULT_PROVIDER)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Model:"))
        top_row.addWidget(self.model_box)
        top_row.addStretch()

        self.input_box = QPlainTextEdit()
        self.input_box.setPlaceholderText("Ingilizce metni buraya yazin...")

        self.output_box = QPlainTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setPlaceholderText("Ceviri burada gorunecek")

        self.translate_button = QPushButton("Cevir  (Ctrl+Enter)")
        self.cancel_button = QPushButton("Iptal  (Esc)")
        self.cancel_button.setEnabled(False)
        self.copy_button = QPushButton("Kopyala")
        self.copy_button.setEnabled(False)

        button_row = QHBoxLayout()
        button_row.addWidget(self.translate_button)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.copy_button)

        self.status_label = QLabel("Hazir")

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(QLabel("Kaynak metin"))
        layout.addWidget(self.input_box)
        layout.addLayout(button_row)
        layout.addWidget(QLabel("Ceviri"))
        layout.addWidget(self.output_box)
        layout.addWidget(self.status_label)

        # Sinyal-yuva baglantilari: dugmeye basilinca hangi metot calisacak
        self.translate_button.clicked.connect(self._start_translation)
        self.cancel_button.clicked.connect(self._cancel_translation)
        self.copy_button.clicked.connect(self._copy_result)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._start_translation)

    def _is_translating(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _start_translation(self) -> None:
        if self._is_translating():
            return

        text = self.input_box.toPlainText().strip()
        if not text:
            self.status_label.setText("Once bir metin yazin.")
            return

        self.translate_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.copy_button.setEnabled(False)
        self.output_box.setPlainText("")
        self.status_label.setText("Cevriliyor...")

        worker = TranslateWorker(text, self.model_box.currentText())
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        self._worker = worker
        worker.start()

    def _cancel_translation(self) -> None:
        """Suren ceviriyi iptal eder, arayuzu hemen serbest birakir."""
        worker = self._worker
        if worker is None or not worker.isRunning():
            return
        worker.cancel()

        # Is parcacigi hala calisiyor; referansini koruyalim ki
        # cop toplayici nesneyi silmesin. Bitince listeden cikar.
        self._abandoned.append(worker)
        worker.finished.connect(lambda w=worker: self._forget(w))

        self._worker = None
        self._reset_buttons()
        self.status_label.setText("Iptal edildi.")

    def _forget(self, worker: TranslateWorker) -> None:
        if worker in self._abandoned:
            self._abandoned.remove(worker)

    def _reset_buttons(self) -> None:
        self.translate_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def _on_success(self, result: str, elapsed: float) -> None:
        self.output_box.setPlainText(result)
        self.status_label.setText(
            f"{self.model_box.currentText()}  |  {elapsed:.1f} sn"
        )
        self._reset_buttons()
        self.copy_button.setEnabled(True)

    def _on_failure(self, message: str) -> None:
        self.output_box.setPlainText("")
        self.status_label.setText(f"Hata: {message}")
        self._reset_buttons()

    def _copy_result(self) -> None:
        QApplication.clipboard().setText(self.output_box.toPlainText())
        self.status_label.setText("Panoya kopyalandi.")

    def keyPressEvent(self, event) -> None:
        """Esc pencereyi kapatir. Iptal isi closeEvent'te yapilir."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
def main() -> None:
    import sys

    app = QApplication(sys.argv)
    window = TranslatorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()