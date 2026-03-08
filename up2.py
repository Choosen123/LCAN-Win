import sys
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox, 
    QLabel, QLineEdit, QHeaderView, QSplitter, QCheckBox, 
    QStatusBar, QToolBar, QAbstractItemView, QDialog, QDialogButtonBox,
    QGridLayout, QStackedWidget, QFrame, QGroupBox, QRadioButton
)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont, QAction, QPainter, QIcon

import gs_usb 

# --- 1. DLC 与 长度的转换常量 ---
# DLC Code -> 实际字节长度
DLC_TO_LEN = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]
# 实际字节长度 -> DLC Code
LEN_TO_DLC = {0:0, 1:1, 2:2, 3:3, 4:4, 5:5, 6:6, 7:7, 8:8, 12:9, 16:10, 20:11, 24:12, 32:13, 48:14, 64:15}
# 发送可选的长度
TX_LEN_OPTIONS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]

# --- 2. 垂直侧边标签 (保持原有设计) ---
class VerticalLabel(QWidget):
    def __init__(self, text, bg_color="#2c3e50"):
        super().__init__()
        self.text = text; self.bg_color = bg_color; self.setFixedWidth(25)
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(self.bg_color)); p.setPen(Qt.GlobalColor.white)
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold)); p.translate(self.width()/2, self.height()/2)
        p.rotate(-90); m = p.fontMetrics(); r = m.boundingRect(self.text)
        p.drawText(int(-r.width()/2), int(r.height()/4), self.text)

# --- 3. 配置弹窗 (略，同前文) ---
class ConfigDialog(QDialog):
    # ... 保持之前的 scan/config 逻辑 ...
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("扫描并配置 CAN 设备"); self.setFixedSize(800, 500); self.selected_dev = None
        layout = QVBoxLayout(self)
        dev_group = QGroupBox(" 可用设备"); dev_lay = QVBoxLayout(dev_group)
        self.btn_scan = QPushButton(" 扫描设备"); self.table_dev = QTableWidget(0, 7)
        self.table_dev.setHorizontalHeaderLabels(["√", "VID", "PID", "总线", "地址", "产品名称", "序列号"])
        dev_lay.addWidget(self.btn_scan); dev_lay.addWidget(self.table_dev); layout.addWidget(dev_group)
        cfg_group = QGroupBox(" CAN 配置"); cfg_lay = QGridLayout(cfg_group)
        self.rb_fd = QRadioButton("CAN FD"); self.rb_fd.setChecked(True)
        self.combo_nom = QComboBox(); self.combo_nom.addItems(["500 kbps", "1000 kbps"])
        self.combo_data = QComboBox(); self.combo_data.addItems(["2000 kbps", "5000 kbps"])
        cfg_lay.addWidget(QLabel("CAN 模式:"), 0, 0); cfg_lay.addWidget(self.rb_fd, 0, 1)
        cfg_lay.addWidget(QLabel("仲裁段:"), 1, 0); cfg_lay.addWidget(self.combo_nom, 1, 1)
        cfg_lay.addWidget(QLabel("数据段:"), 2, 0); cfg_lay.addWidget(self.combo_data, 2, 1)
        layout.addWidget(cfg_group)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)
        self.btn_scan.clicked.connect(self.scan)
        self.table_dev.itemClicked.connect(self.on_select)
    def scan(self):
        self.table_dev.setRowCount(0); devs = gs_usb.scan_devices()
        for d in [x for x in devs if x.is_candlelight]:
            r = self.table_dev.rowCount(); self.table_dev.insertRow(r)
            it = QTableWidgetItem(); it.setCheckState(Qt.CheckState.Unchecked); self.table_dev.setItem(r, 0, it)
            self.table_dev.setItem(r, 1, QTableWidgetItem(hex(d.vid))); self.table_dev.setItem(r, 5, QTableWidgetItem(d.product))
            self.table_dev.item(r, 0).setData(Qt.ItemDataRole.UserRole, (d.vid, d.pid))
    def on_select(self, it):
        for r in range(self.table_dev.rowCount()): self.table_dev.item(r, 0).setCheckState(Qt.CheckState.Unchecked)
        self.table_dev.item(it.row(), 0).setCheckState(Qt.CheckState.Checked)
        self.selected_dev = self.table_dev.item(it.row(), 0).data(Qt.ItemDataRole.UserRole)
    def get_config(self):
        return {"device": self.selected_dev, "nom": int(self.combo_nom.currentText().split(' ')[0])*1000, "data": int(self.combo_data.currentText().split(' ')[0])*1000, "fd": self.rb_fd.isChecked()}

# --- 4. 主界面 ---
class PCANViewPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GsUsb-View Pro")
        self.resize(1200, 850)
        self.device = None
        self.rx_map = {}
        self.tx_list = []
        self.config = None
        self.init_ui(); self.apply_style()
        self.ui_timer = QTimer(); self.ui_timer.timeout.connect(self.update_ui); self.ui_timer.start(50)
        self.tx_timer = QTimer(); self.tx_timer.timeout.connect(self.process_tx); self.tx_timer.start(1)

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f0f0f0; }
            #ViewSelectorBar { background-color: #34495e; min-height: 40px; }
            QPushButton#TabButton { background-color: transparent; color: #ecf0f1; border: none; padding: 8px 20px; font-size: 12px; margin-top: 5px; }
            QPushButton#TabButton[active="true"] { background-color: #fff5d7; color: #2c3e50; font-weight: bold; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTableWidget { gridline-color: #dcdcdc; font-family: 'Consolas'; font-size: 10pt; }
            QHeaderView::section { background-color: #f2f2f2; font-weight: bold; border: 1px solid #dcdcdc; }
        """)

    def init_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        layout = QVBoxLayout(central); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        
        # 工具栏
        t = self.addToolBar("Main")
        act_setup = QAction(self.style().standardIcon(QApplication.style().StandardPixmap.SP_DriveNetIcon), "Setup", self)
        act_setup.triggered.connect(self.show_config); t.addAction(act_setup)
        self.act_conn = QAction(self.style().standardIcon(QApplication.style().StandardPixmap.SP_MediaPlay), "Connect", self)
        self.act_conn.triggered.connect(self.toggle_connection); t.addAction(self.act_conn)
        t.addSeparator()
        act_msg = QAction(self.style().standardIcon(QApplication.style().StandardPixmap.SP_FileIcon), "New Msg", self)
        act_msg.triggered.connect(lambda: self.add_tx_row("123h", 1, 16, "00 11 22 33 44 55 66 77 88 99 AA BB CC DD EE FF", 100))
        t.addAction(act_msg)

        # 标签栏
        v = QFrame(); v.setObjectName("ViewSelectorBar"); vb = QHBoxLayout(v); layout.addWidget(v)
        self.btn_main = QPushButton(" Receive / Transmit"); self.btn_main.setObjectName("TabButton")
        self.btn_trace = QPushButton(" Trace"); self.btn_trace.setObjectName("TabButton")
        self.btn_main.setProperty("active", "true")
        self.btn_main.clicked.connect(lambda: self.switch_view(0)); self.btn_trace.clicked.connect(lambda: self.switch_view(1))
        vb.addWidget(self.btn_main); vb.addWidget(self.btn_trace); vb.addStretch()

        # 容器
        self.stack = QStackedWidget(); layout.addWidget(self.stack)
        self.split = QSplitter(Qt.Orientation.Vertical)
        
        # --- Receive Table ---
        r_w = QWidget(); r_l = QHBoxLayout(r_w); r_l.setContentsMargins(0,0,0,0); r_l.setSpacing(0)
        r_l.addWidget(VerticalLabel("RECEIVE", "#2980b9"))
        self.table_rx = QTableWidget(0, 6)
        self.table_rx.setHorizontalHeaderLabels(["ID", "Type", "Length", "Data", "Cycle Time", "Count"])
        self.table_rx.setWordWrap(True); self.table_rx.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        r_l.addWidget(self.table_rx); self.split.addWidget(r_w)

        # --- Transmit Table ---
        t_w = QWidget(); t_l = QHBoxLayout(t_w); t_l.setContentsMargins(0,0,0,0); t_l.setSpacing(0)
        t_l.addWidget(VerticalLabel("TRANSMIT", "#27ae60"))
        self.table_tx = QTableWidget(0, 7)
        self.table_tx.setHorizontalHeaderLabels(["ID", "Type", "Length", "Data", "Cycle Time", "Count", "Comment"])
        self.table_tx.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        t_l.addWidget(self.table_tx); self.split.addWidget(t_w)
        
        self.split.setSizes([500, 300]); self.stack.addWidget(self.split)
        
        # --- Trace Table ---
        self.table_trace = QTableWidget(0, 5)
        self.table_trace.setHorizontalHeaderLabels(["Idx", "Time", "ID", "Len", "Data"])
        self.table_trace.setWordWrap(True); self.table_trace.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.stack.addWidget(self.table_trace)

    def switch_view(self, idx):
        self.stack.setCurrentIndex(idx)
        self.btn_main.setProperty("active", "true" if idx==0 else "false")
        self.btn_trace.setProperty("active", "true" if idx==1 else "false")
        for b in [self.btn_main, self.btn_trace]: b.style().unpolish(b); b.style().polish(b); b.update()

    def show_config(self):
        dlg = ConfigDialog(self)
        if dlg.exec(): self.config = dlg.get_config()

    def toggle_connection(self):
        if not self.device:
            if not self.config: self.show_config()
            if not self.config: return
            try:
                vid, pid = self.config['device']
                self.device = gs_usb.GsUsbFDCAN(vid, pid)
                self.device.setup(self.config['nom'], self.config['data'])
                self.device.start(True)
                self.rx_t = ReceiveThread(self.device); self.rx_t.frames_signal.connect(self.on_frames); self.rx_t.start()
                self.act_conn.setIcon(self.style().standardIcon(QApplication.style().StandardPixmap.SP_MediaStop))
            except Exception as e: print(e)
        else:
            self.rx_t.running = False; self.device.stop(); self.device = None
            self.act_conn.setIcon(self.style().standardIcon(QApplication.style().StandardPixmap.SP_MediaPlay))

    def on_frames(self, frames):
        now = time.time()
        for f in frames:
            cid = f['can_id']
            # 关键修复1：根据 DLC Code 转换实际显示长度，确保 Data 字段完整
            actual_len = DLC_TO_LEN[f['dlc']] if f['dlc'] < 16 else len(f['data'])
            data_s = " ".join(f"{b:02X}" for b in f['data'])
            
            if cid not in self.rx_map:
                r = self.table_rx.rowCount(); self.table_rx.insertRow(r)
                for i in range(6): self.table_rx.setItem(r, i, QTableWidgetItem(""))
                self.rx_map[cid] = {"row": r, "cnt": 0, "pts": now}
            
            m = self.rx_map[cid]
            m['cnt'] += 1; m['cyc'] = (now - m['pts'])*1000 if m['cnt'] > 1 else 0; m['pts'] = now
            m['data'] = data_s; m['len'] = actual_len; m['is_fd'] = f['is_fd']

            # 更新 Trace
            tr = self.table_trace.rowCount()
            if tr > 500: self.table_trace.removeRow(0); tr -= 1
            self.table_trace.insertRow(tr)
            self.table_trace.setItem(tr, 0, QTableWidgetItem(str(tr)))
            self.table_trace.setItem(tr, 1, QTableWidgetItem(f"{f['timestamp']:.4f}"))
            self.table_trace.setItem(tr, 2, QTableWidgetItem(f"{cid:03X}h"))
            self.table_trace.setItem(tr, 3, QTableWidgetItem(str(actual_len)))
            self.table_trace.setItem(tr, 4, QTableWidgetItem(data_s))
            self.table_trace.resizeRowToContents(tr)

    def update_ui(self):
        for cid, m in self.rx_map.items():
            r = m['row']
            self.table_rx.item(r, 0).setText(f"{cid:03X}h")
            self.table_rx.item(r, 1).setText("CAN FD" if m['is_fd'] else "CAN")
            self.table_rx.item(r, 2).setText(str(m['len']))
            self.table_rx.item(r, 3).setText(m['data'])
            self.table_rx.item(r, 4).setText(f"{m['cyc']:.1f}")
            self.table_rx.item(r, 5).setText(str(m['cnt']))
            self.table_rx.resizeRowToContents(r)

    def add_tx_row(self, id_h, type_idx, len_val, data_s, cyc):
        row = self.table_tx.rowCount(); self.table_tx.insertRow(row)
        self.table_tx.setItem(row, 0, QTableWidgetItem(id_h))
        
        # 关键修复2：Type 下拉框
        type_cb = QComboBox()
        type_cb.addItems(["Classic CAN", "CAN FD", "CAN FD (BRS)"])
        type_cb.setCurrentIndex(type_idx)
        self.table_tx.setCellWidget(row, 1, type_cb)
        
        # 关键修复3：Length 下拉框 (显示实际长度)
        len_cb = QComboBox()
        len_cb.addItems([str(x) for x in TX_LEN_OPTIONS])
        len_cb.setCurrentText(str(len_val))
        self.table_tx.setCellWidget(row, 2, len_cb)
        
        self.table_tx.setItem(row, 3, QTableWidgetItem(data_s))
        
        cw = QWidget(); cl = QHBoxLayout(cw); cl.setContentsMargins(5,0,5,0)
        cb = QCheckBox(); ed = QLineEdit(str(cyc)); ed.setFixedWidth(40)
        cl.addWidget(cb); cl.addWidget(ed); cl.addWidget(QLabel("ms"))
        self.table_tx.setCellWidget(row, 4, cw)
        
        self.table_tx.setItem(row, 5, QTableWidgetItem("0"))
        self.table_tx.setItem(row, 6, QTableWidgetItem(""))
        
        # 绑定引用供后台处理
        self.tx_list.append({"row": row, "type_cb": type_cb, "len_cb": len_cb, "cb": cb, "ed": ed, "last": 0, "cnt": 0})

    def process_tx(self):
        if not self.device: return
        now_ms = time.time() * 1000
        for tx in self.tx_list:
            if tx['cb'].isChecked():
                try:
                    c = float(tx['ed'].text())
                    if now_ms - tx['last'] >= c:
                        r = tx['row']
                        
                        # 1. 解析 ID
                        id_str = self.table_tx.item(r, 0).text().replace("h","")
                        cid = int(id_str, 16)
                        
                        # 2. 从 Type 下拉框获取模式
                        # 假设下拉框内容是 ["Classic CAN", "CAN FD", "CAN FD (BRS)"]
                        type_str = tx['type_cb'].currentText()
                        is_fd = "CAN FD" in type_str
                        is_brs = "(BRS)" in type_str
                        
                        # 3. 获取长度并准备数据
                        target_len = int(tx['len_cb'].currentText())
                        raw_hex = self.table_tx.item(r, 3).text().replace(" ","")
                        data_bytes = bytearray.fromhex(raw_hex)
                        
                        # 自动截断或补齐数据
                        if len(data_bytes) < target_len:
                            data_bytes.extend([0] * (target_len - len(data_bytes)))
                        else:
                            data_bytes = data_bytes[:target_len]
                        
                        # 4. 调用新的 send_frame (注意参数增加了 is_fd)
                        # 即使你的 C++ 导出名还是 send_fd_frame，也要传这个 bool
                        if self.device.send_frame(cid, bytes(data_bytes), is_fd, is_brs):
                            tx['cnt'] += 1
                            self.table_tx.item(r, 5).setText(str(tx['cnt']))
                            tx['last'] = now_ms
                except Exception as e:
                    print(f"TX Process Error: {e}")

class ReceiveThread(QThread):
    frames_signal = pyqtSignal(list)
    def __init__(self, device):
        super().__init__(); self.device = device; self.running = True
    def run(self):
        while self.running:
            if self.device:
                f = self.device.get_received_frames(100)
                if f: self.frames_signal.emit(f)
            self.msleep(10)

if __name__ == "__main__":
    a = QApplication(sys.argv); a.setStyle("Fusion")
    w = PCANViewPro(); w.show(); sys.exit(a.exec())