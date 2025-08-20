import os
import sys
import cv2
import time
import random
import threading
import subprocess
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QCheckBox, QPushButton, QTextEdit,
    QHeaderView, QLabel, QTabWidget, QFrame, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt5.QtGui import QIcon
ADB_PATH = "adb\\adb.exe"
DATA_PATH = "data"
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
connected_devices = set()
def get_ldplayer_devices():
    result = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()[1:]
    devices = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        device_id = parts[0]
        if device_id.startswith("emulator-"):
            devices.append(device_id)
    return devices
def auto_connect(dev):
    if dev in connected_devices:
        return
    try:
        port_num = int(dev.split("-")[-1]) + 1
        ip_port = f"127.0.0.1:{port_num}"
        subprocess.run([ADB_PATH, "connect", ip_port], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        connected_devices.add(dev)
    except Exception:
        pass
def launch_game(dev, package_name):
    subprocess.run([ADB_PATH, "-s", dev, "shell", "monkey", "-p", package_name,
                    "-c", "android.intent.category.LAUNCHER", "1"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def close_game(dev, package_name):
    subprocess.run([ADB_PATH, "-s", dev, "shell", "am", "force-stop", package_name],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def screenshot_path_for(dev: str) -> str:
    safe = dev.replace(":", "_")
    return str(CACHE_DIR / f"{safe}.png")
def adb_screencap(device_id: str, output: str):
    subprocess.run([ADB_PATH, "-s", device_id, "shell", "screencap", "-p", "/sdcard/screen.png"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([ADB_PATH, "-s", device_id, "pull", "/sdcard/screen.png", output],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def adb_tap(device_id: str, x: int, y: int):
    subprocess.run([ADB_PATH, "-s", device_id, "shell", "input", "tap", str(x), str(y)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def find_image(target_path: str, screenshot_path: str, threshold: float = 0.85):
    if not os.path.exists(target_path):
        return None
    img_rgb = cv2.imread(screenshot_path)
    template = cv2.imread(target_path)
    if img_rgb is None or template is None:
        return None
    res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val >= threshold:
        cx = int(max_loc[0] + template.shape[1] / 2)
        cy = int(max_loc[1] + template.shape[0] / 2)
        return (cx, cy)
    return None
def wait_and_click(device_id: str, filename: str, screenshot_path: str, must: bool = True,
                   delay: float = 1.0, threshold: float = 0.85, click_fn=None, jitter: int = 0,
                   stop_event: threading.Event = None) -> bool:
    path = os.path.join(DATA_PATH, filename)
    while not (stop_event and stop_event.is_set()):
        adb_screencap(device_id, screenshot_path)
        coord = find_image(path, screenshot_path=screenshot_path, threshold=threshold)
        if coord:
            x, y = coord
            if click_fn:
                click_fn(device_id, x, y, jitter)
            else:
                adb_tap(device_id, x, y)
            time.sleep(delay)
            return True
        if not must:
            return False
        time.sleep(0.8)
    return False
def antiban_pause():
    time.sleep(random.uniform(2.8, 12.2))
def anti_ban_tap(device_id: str, x: int, y: int, jitter: int = 6):
    dx = random.randint(-jitter, jitter)
    dy = random.randint(-jitter, jitter)
    jittered = (max(1, x + dx), max(1, y + dy))
    time.sleep(random.uniform(0.05, 0.25))
    adb_tap(device_id, *jittered)
    time.sleep(random.uniform(0.05, 0.2))
    if random.random() < 0.2:
        antiban_pause()
class LogBus(QObject):
    sig = pyqtSignal(str)
    captcha = pyqtSignal(str)
class FogWorker(threading.Thread):
    def __init__(self, device_id: str, use_antiban: bool, check_captcha: bool, log_bus: LogBus, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.device_id = device_id
        self.use_antiban = use_antiban
        self.check_captcha = check_captcha
        self.log_bus = log_bus
        self.stop_event = stop_event
        self.ssp = screenshot_path_for(device_id)
    def _tap(self, x, y):
        if self.use_antiban:
            anti_ban_tap(self.device_id, x, y)
        else:
            adb_tap(self.device_id, x, y)
    def _log(self, msg):
        self.log_bus.sig.emit(msg)
    def _find_and_tap(self, img, must=True, delay=1.0, thr=0.85):
        clicked = wait_and_click(
            self.device_id, img, self.ssp, must=must, delay=delay, threshold=thr,
            click_fn=anti_ban_tap if self.use_antiban else None, jitter=6, stop_event=self.stop_event
        )
        return clicked
    def check_for_captcha(self):
        for i in range(1, 4):
            if find_image(os.path.join(DATA_PATH, f"captcha{i}.png"), self.ssp, threshold=0.8):
                return True
        return False
    def run(self):
        self._log(f"Bắt đầu xóa sương mù {self.device_id} | Anti-ban: {'ON' if self.use_antiban else 'OFF'}")
        try:
            while not self.stop_event.is_set():
                adb_screencap(self.device_id, self.ssp)
                if self.check_captcha:
                    if self.check_for_captcha():
                        self._log(f"Phát hiện captcha {self.device_id} !")
                        self.log_bus.captcha.emit(self.device_id)
                        self.stop_event.set()
                        break
                adb_screencap(self.device_id, self.ssp)
                home = find_image(os.path.join(DATA_PATH, "home.png"), self.ssp)
                map_ = find_image(os.path.join(DATA_PATH, "map.png"), self.ssp)
                if home:
                    self._tap(*home)
                    time.sleep(1.2)
                elif map_:
                    self._tap(*map_)
                    time.sleep(1.2)
                    adb_screencap(self.device_id, self.ssp)
                    home2 = find_image(os.path.join(DATA_PATH, "home.png"), self.ssp)
                    if home2:
                        self._tap(*home2)
                        time.sleep(1.0)
                adb_screencap(self.device_id, self.ssp)
                target = None
                for i in range(1, 3):
                    coord = find_image(os.path.join(DATA_PATH, f"{i}.png"), self.ssp)
                    if coord:
                        target = coord
                        break
                if not target:
                    time.sleep(1.0)
                    continue
                self._tap(*target)
                time.sleep(1.0)
                self._find_and_tap("scout.png", must=False, delay=1.2)
                self._find_and_tap("explore.png", must=True, delay=1.2)
                adb_screencap(self.device_id, self.ssp)
                if not find_image(os.path.join(DATA_PATH, "selected.png"), self.ssp):
                    coord = find_image(os.path.join(DATA_PATH, "notselected.png"), self.ssp)
                    if coord:
                        self._tap(*coord)
                        time.sleep(0.8)
                self._find_and_tap("explore.png", must=True, delay=1.6)
                self._find_and_tap("send.png", must=True, delay=1.2)
                if self.use_antiban and random.random() < 0.25:
                    self._log(f"⏳ {self.device_id} tạm dừng anti-ban")
                    antiban_pause()

            self._log(f"Đã dừng xóa sương mù {self.device_id} !")
        except Exception as e:
            self._log(f"Lỗi {self.device_id}: {e}")
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rise Of Kingdoms")
        self.setWindowIcon(QIcon("logo.png"))
        self.resize(250, 500)
        self.workers = {}
        self.stop_events = {}
        self.log_bus = LogBus()
        self.log_bus.sig.connect(self.log)
        self.log_bus.captcha.connect(self.captcha_alert)
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(6, 6, 6, 6)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["#", "Emulator", "Trạng thái"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setStyleSheet(
            """
            QTableWidget { border: 1px solid gray; }
            QHeaderView::section { border: 1px solid gray; background-color: #f0f0f0; }
            QTableWidget::item { border: 1px solid gray; }
            """
        )
        frame_emulator = QFrame()
        vbox_emulator = QVBoxLayout()
        vbox_emulator.setContentsMargins(0, 0, 0, 0)
        vbox_emulator.addWidget(self.table)
        frame_emulator.setLayout(vbox_emulator)
        main_layout.addWidget(frame_emulator)
        frame_logs = QFrame()
        vbox_logs = QVBoxLayout()
        vbox_logs.setContentsMargins(0, 0, 0, 0)

        lbl_logs = QLabel("Activity Logs")
        lbl_logs.setStyleSheet(
            """
            background-color: #f0f0f0;
            font-weight: bold;
            padding: 4px;
            border: 1px solid gray;
            """
        )
        vbox_logs.addWidget(lbl_logs)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setStyleSheet("border: 1px solid gray; border-top: none;")
        vbox_logs.addWidget(self.logs)
        frame_logs.setLayout(vbox_logs)
        main_layout.addWidget(frame_logs)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane { border: 1px solid gray; }
            QTabBar::tab { padding: 6px; }
            """
        )
        self.tab_control = QWidget()
        layout_control = QVBoxLayout()
        hbox_global = QHBoxLayout()
        self.btn_open_game_global = QPushButton("Open Global")
        self.btn_close_game_global = QPushButton("Close Global")
        hbox_global.addWidget(self.btn_open_game_global)
        hbox_global.addWidget(self.btn_close_game_global)
        layout_control.addLayout(hbox_global)
        hbox_vn = QHBoxLayout()
        self.btn_open_game_vn = QPushButton("Open VN")
        self.btn_close_game_vn = QPushButton("Close VN")
        hbox_vn.addWidget(self.btn_open_game_vn)
        hbox_vn.addWidget(self.btn_close_game_vn)
        layout_control.addLayout(hbox_vn)
        self.tab_control.setLayout(layout_control)
        self.tabs.addTab(self.tab_control, "Game")
        self.tab_scout = QWidget()
        layout_scout = QVBoxLayout()
        row1 = QHBoxLayout()
        self.chk_explore_fog = QCheckBox("Explore fog")
        self.chk_antiban = QCheckBox("Anti-ban")
        self.chk_captcha = QCheckBox("Warning captcha")
        row1.addWidget(self.chk_explore_fog)
        row1.addWidget(self.chk_antiban)
        row1.addWidget(self.chk_captcha)
        layout_scout.addLayout(row1)
        row2 = QHBoxLayout()
        self.btn_start_scout = QPushButton("Start")
        self.btn_stop_scout = QPushButton("Stop")
        row2.addWidget(self.btn_start_scout)
        row2.addWidget(self.btn_stop_scout)
        layout_scout.addLayout(row2)
        self.tab_scout.setLayout(layout_scout)
        self.tabs.addTab(self.tab_scout, "Trinh Sát")
        frame_tabs = QFrame()
        vbox_tabs = QVBoxLayout()
        vbox_tabs.setContentsMargins(0, 0, 0, 0)
        vbox_tabs.addWidget(self.tabs)
        frame_tabs.setLayout(vbox_tabs)
        main_layout.addWidget(frame_tabs)
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        self.btn_open_game_global.clicked.connect(lambda: self.launch_close_game("open", "com.lilithgame.roc.gp"))
        self.btn_close_game_global.clicked.connect(lambda: self.launch_close_game("close", "com.lilithgame.roc.gp"))
        self.btn_open_game_vn.clicked.connect(lambda: self.launch_close_game("open", "com.rok.gp.vn"))
        self.btn_close_game_vn.clicked.connect(lambda: self.launch_close_game("close", "com.rok.gp.vn"))
        self.btn_start_scout.clicked.connect(self.start_scout)
        self.btn_stop_scout.clicked.connect(self.stop_scout)
        self.timer = QTimer()
        self.timer.timeout.connect(self.scan_and_connect)
        self.timer.start(3000)
        self.scan_and_connect()
    def log(self, msg):
        now = time.strftime("%H:%M:%S")
        self.logs.append(f"{now} - {msg}")
    def captcha_alert(self, dev):
        QMessageBox.warning(self, "Captcha Warning", f"Phát hiện captcha {dev}, đã dừng !")
    def get_selected_devices(self):
        devices = []
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                chk = widget.layout().itemAt(0).widget()
                if chk and chk.isChecked():
                    dev = self.table.item(row, 1).text()
                    devices.append(dev)
        return devices
    def launch_close_game(self, action, pkg):
        selected = self.get_selected_devices()
        if not selected:
            self.log("Chưa chọn thiết bị nào để thao tác !")
            return
        for dev in selected:
            try:
                if action == "open":
                    launch_game(dev, pkg)
                    self.log(f"Đã mở game ({pkg}) trên {dev}")
                else:
                    close_game(dev, pkg)
                    self.log(f"Đã đóng game ({pkg}) trên {dev}")
            except Exception as e:
                self.log(f"Lỗi thao tác game trên {dev}: {e}")
    def scan_and_connect(self):
        try:
            previously_selected = set(self.get_selected_devices())
            devices = get_ldplayer_devices()
            for dev in devices:
                auto_connect(dev)
            self.table.setRowCount(len(devices))
            for row, dev in enumerate(devices):
                chk = QCheckBox()
                if dev in previously_selected:
                    chk.setChecked(True)
                layout = QHBoxLayout()
                layout.addWidget(chk)
                layout.setAlignment(Qt.AlignCenter)
                layout.setContentsMargins(0, 0, 0, 0)
                w = QWidget()
                w.setLayout(layout)
                self.table.setCellWidget(row, 0, w)
                item_dev = QTableWidgetItem(dev)
                item_dev.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 1, item_dev)
                item_status = QTableWidgetItem("🟢 Đã kết nối" if dev in connected_devices else "🔴 Lỗi")
                item_status.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 2, item_status)
        except Exception as e:
            self.log(f"Lỗi quét thiết bị: {e}")
    def start_scout(self):
        selected = self.get_selected_devices()
        if not selected:
            self.log("Chưa chọn thiết bị để dùng lệnh !")
            return
        if not self.chk_explore_fog.isChecked():
            self.log("Vui lòng select explore fog để bắt đầu.")
            return

        use_antiban = self.chk_antiban.isChecked()
        check_captcha = self.chk_captcha.isChecked()

        for dev in selected:
            if dev in self.workers and self.workers[dev].is_alive():
                self.log(f"{dev} đang chạy rồi !")
                continue
            stop_event = threading.Event()
            self.stop_events[dev] = stop_event
            worker = FogWorker(dev, use_antiban, check_captcha, self.log_bus, stop_event)
            self.workers[dev] = worker
            worker.start()
            self.log(f"Bắt đầu xóa sương mù {dev}")
    def stop_scout(self):
        selected = self.get_selected_devices()
        if not selected:
            targets = list(self.stop_events.keys())
        else:
            targets = selected
        for dev in targets:
            ev = self.stop_events.get(dev)
            if ev and not ev.is_set():
                ev.set()
                self.log(f"Đang dừng {dev}")
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
