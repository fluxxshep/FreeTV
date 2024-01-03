from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from modem import ArqModem, list_audio_devices
from imagecodecs import avif_encode, avif_decode, AvifError
import numpy as np
import cv2
import time

# import faulthandler
# faulthandler.enable()


class ModemSignals(QObject):
    rx_signal = Signal(bytes)
    transmit_on_off_signal = Signal(bool)
    rx_callsign_signal = Signal(str)


class ModemWorker(QObject):
    def __init__(self, callsign, in_device, out_device):
        super().__init__()
        self.modem = ArqModem(in_device, out_device, callsign)
        self.run = True
        self.is_transmitting = False
        self.signal = ModemSignals()
        self.tx_data = None
        self.retransmit = False

    def work(self):
        while self.run:
            if self.retransmit:
                self.modem.tx_retransmit_request()
                self.retransmit = False

            elif not self.is_transmitting:
                self.modem.arq_rx()
                rx_data = self.modem.get_rx_data()

                rx_callsign = self.modem.get_rx_callsign()
                if rx_callsign is not None:
                    self.signal.rx_callsign_signal.emit(rx_callsign)

                if rx_data is not None:

                    self.signal.rx_signal.emit(rx_data)

            elif self.tx_data:
                self.signal.transmit_on_off_signal.emit(True)
                self.modem.arq_tx(self.tx_data)
                self.tx_data = None
                self.is_transmitting = False
                self.signal.transmit_on_off_signal.emit(False)

        self.modem.close()
        self.thread().quit()

    def stop(self):
        self.run = False

    def request_retransmit(self):
        if self.modem.check_missed_frames() is not None:
            self.retransmit = True

    def transmit(self, data):
        self.is_transmitting = True
        self.tx_data = data


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('FreeTV')

        self.in_devices, self.out_devices = list_audio_devices()
        self.in_device = int(next(iter(self.in_devices)))
        self.out_device = int(next(iter(self.out_devices)))

        self.callsign = '-CALLSIGN-'
        self.modem = None
        self.modem_transmitting = False
        self.modem_thread = None

        # setup widgets

        # settings
        self.central_widget = QWidget()
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setSpacing(0)
        self.main_layout.addStretch(1)

        self.settings_widget = QWidget()
        self.main_layout.addWidget(self.settings_widget)

        self.callsign_input_label = QLabel('My callsign')
        self.callsign_input_label.setFont(QFont('Arial', 15))

        self.callsign_input = QLineEdit()
        self.callsign_input.textChanged.connect(self.set_callsign)

        self.in_device_select = QComboBox()
        self.in_device_select.addItems(self.in_devices.values())
        self.in_device_select.currentTextChanged.connect(self.change_input_device)

        self.out_device_select = QComboBox()
        self.out_device_select.addItems(self.out_devices.values())
        self.out_device_select.currentTextChanged.connect(self.change_output_device)

        self.modem_start_button = QPushButton('Modem start / stop')
        self.modem_start_button.clicked.connect(self.start_stop_modem)
        self.modem_start_button.setAutoFillBackground(True)
        modem_button_palette = self.modem_start_button.palette()
        modem_button_palette.setColor(self.modem_start_button.backgroundRole(), Qt.GlobalColor.red)
        self.modem_start_button.setPalette(modem_button_palette)

        self.settings_label = QLabel('Settings')
        self.settings_label.setFont(QFont('Arial', 25))

        self.settings_layout = QVBoxLayout(self.settings_widget)
        self.settings_layout.addWidget(self.settings_label)
        self.settings_layout.addWidget(self.callsign_input_label)
        self.settings_layout.addWidget(self.callsign_input)
        self.settings_layout.addWidget(self.in_device_select)
        self.settings_layout.addWidget(self.out_device_select)
        self.settings_layout.addWidget(self.modem_start_button)
        self.settings_layout.setSpacing(0)
        self.settings_layout.addStretch(1)

        # receiver
        self.rx_widget = QWidget()
        self.main_layout.addWidget(self.rx_widget)

        self.rx_label = QLabel('Receive')
        self.rx_label.setFont(QFont('Arial', 25))

        self.image_x = 500
        self.image_y = 500

        self.rx_image = np.ones(shape=(self.image_x, self.image_y, 3), dtype=np.uint8) * 100
        self.rx_image_frame = QLabel()
        self.update_rx_image(self.rx_image)

        self.rx_callsign_label = QLabel('RX callsign: -none yet!-')
        self.rx_error_label = QLabel('No RX errors!')
        self.rx_error_label.setAutoFillBackground(True)

        rx_error_palette = self.rx_error_label.palette()
        rx_error_palette.setColor(self.rx_error_label.backgroundRole(), Qt.GlobalColor.green)
        self.rx_error_label.setPalette(rx_error_palette)

        self.request_retransmit_button = QPushButton('Request retransmit')
        self.request_retransmit_button.setAutoFillBackground(True)
        request_retransmit_palette = self.request_retransmit_button.palette()
        request_retransmit_palette.setColor(self.request_retransmit_button.backgroundRole(), Qt.GlobalColor.red)
        self.request_retransmit_button.setPalette(request_retransmit_palette)
        self.request_retransmit_button.clicked.connect(self.request_retransmit)

        self.rx_layout = QVBoxLayout(self.rx_widget)
        self.rx_layout.addWidget(self.rx_label)
        self.rx_layout.addWidget(self.rx_image_frame)
        self.rx_layout.addWidget(self.rx_callsign_label)
        self.rx_layout.addWidget(self.rx_error_label)
        self.rx_layout.addWidget(self.request_retransmit_button)
        self.rx_layout.setSpacing(0)
        self.rx_layout.addStretch(1)

        # transmit
        self.tx_widget = QWidget()
        self.main_layout.addWidget(self.tx_widget)

        self.tx_label = QLabel('Transmit')
        self.tx_label.setFont(QFont('Arial', 25))

        self.tx_image = np.ones(shape=(self.image_x, self.image_y, 3), dtype=np.uint8) * 100
        self.tx_image_frame = QLabel()
        self.update_tx_image(self.tx_image)

        self.select_tx_image_button = QPushButton('Select TX image')
        self.select_tx_image_button.clicked.connect(self.select_tx_image)

        self.tx_button = QPushButton('Transmit!')
        self.tx_button.setAutoFillBackground(True)
        tx_button_palette = self.tx_button.palette()
        tx_button_palette.setColor(self.tx_button.backgroundRole(), Qt.GlobalColor.yellow)
        self.tx_button.setPalette(tx_button_palette)
        self.tx_button.clicked.connect(self.transmit_image)

        self.tx_layout = QVBoxLayout(self.tx_widget)
        self.tx_layout.addWidget(self.tx_label)
        self.tx_layout.addWidget(self.tx_image_frame)
        self.tx_layout.addWidget(self.select_tx_image_button)
        self.tx_layout.addWidget(self.tx_button)
        self.tx_layout.setSpacing(0)
        self.tx_layout.addStretch(1)

        self.setCentralWidget(self.central_widget)

    def start_stop_modem(self):
        if self.modem is None:
            self.modem = ModemWorker(self.callsign, self.in_device, self.out_device)
            self.modem_thread = QThread()
            self.modem.moveToThread(self.modem_thread)
            self.modem_thread.started.connect(self.modem.work)
            self.modem_thread.start()

            self.modem.signal.transmit_on_off_signal.connect(self.modem_transmitting_on_off)
            self.modem.signal.rx_callsign_signal.connect(self.update_rx_callsign)
            self.modem.signal.rx_signal.connect(self.process_rx)

            modem_button_palette = self.modem_start_button.palette()
            modem_button_palette.setColor(self.modem_start_button.backgroundRole(), Qt.GlobalColor.green)
            self.modem_start_button.setPalette(modem_button_palette)
        else:
            self.modem.stop()
            time.sleep(0.25)
            self.modem = None

            modem_button_palette = self.modem_start_button.palette()
            modem_button_palette.setColor(self.modem_start_button.backgroundRole(), Qt.GlobalColor.red)
            self.modem_start_button.setPalette(modem_button_palette)

    def change_input_device(self, name):
        self.in_device = int(list(self.in_devices.keys())[list(self.in_devices.values()).index(name)])

    def change_output_device(self, name):
        self.out_device = int(list(self.out_devices.keys())[list(self.out_devices.values()).index(name)])

    def set_callsign(self, callsign):
        self.callsign = callsign

    def update_rx_image(self, image):
        self.rx_image = QImage(image.data, image.shape[1], image.shape[0], QImage.Format.Format_RGB888).rgbSwapped()
        self.rx_image_frame.setPixmap(QPixmap.fromImage(self.rx_image))

    def update_tx_image(self, image):
        tx_image = QImage(image.data, image.shape[1], image.shape[0], QImage.Format.Format_RGB888).rgbSwapped()
        self.tx_image_frame.setPixmap(QPixmap.fromImage(tx_image))

    def update_rx_callsign(self, callsign):
        self.rx_callsign_label.setText(f'RX callsign: {callsign}')

    def update_rx_error_text(self, error):
        if error:
            self.rx_error_label.setText('RX error!')
            p = self.rx_error_label.palette()
            p.setColor(self.rx_error_label.backgroundRole(), Qt.GlobalColor.red)
            self.rx_error_label.setPalette(p)
        else:
            self.rx_error_label.setText('No RX errors!')
            p = self.rx_error_label.palette()
            p.setColor(self.rx_error_label.backgroundRole(), Qt.GlobalColor.green)
            self.rx_error_label.setPalette(p)

    def request_retransmit(self):
        if self.modem is not None:
            self.modem.request_retransmit()

    def select_tx_image(self):
        dialog = QFileDialog(self)
        dialog.setDirectory('./')
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setNameFilter("Images (*.png *.jpg)")
        dialog.setViewMode(QFileDialog.ViewMode.List)

        if dialog.exec():
            filename = dialog.selectedFiles()[0]
            if filename:
                tx_image = cv2.imread(filename)
                self.tx_image = cv2.resize(tx_image, (self.image_x, self.image_y))
                self.update_tx_image(self.tx_image)

    def modem_transmitting_on_off(self, modem_transmitting):
        self.modem_transmitting = modem_transmitting

        if modem_transmitting:
            tx_button_palette = self.tx_button.palette()
            tx_button_palette.setColor(self.tx_button.backgroundRole(), Qt.GlobalColor.red)
            self.tx_button.setPalette(tx_button_palette)
        else:
            tx_button_palette = self.tx_button.palette()
            tx_button_palette.setColor(self.tx_button.backgroundRole(), Qt.GlobalColor.yellow)
            self.tx_button.setPalette(tx_button_palette)

    def process_rx(self, rx_data):
        image = None
        try:
            image = avif_decode(rx_data)
            self.update_rx_error_text(False)

        except AvifError:
            self.update_rx_error_text(True)

        if image is not None:
            self.rx_image = image
            self.update_rx_image(self.rx_image)

    def transmit_image(self):
        if self.modem is not None and not self.modem_transmitting:
            compressed_image = avif_encode(self.tx_image, level=10)
            self.modem.transmit(compressed_image)

    def closeEvent(self, event):
        if self.modem:
            self.modem.stop()
            time.sleep(0.25)


if __name__ == '__main__':
    app = QApplication([])

    window = MainWindow()
    window.show()

    app.exec()
