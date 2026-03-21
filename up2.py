import os
import re
import subprocess
import sys
import time
import traceback


# --- 1. 代理执行逻辑：负责替换文件 ---
def run_updater_worker():
    # 命令行参数: [0]脚本 [1]--updater-mode [2]旧PID [3]目标EXE路径 [4]新EXE路径
    if len(sys.argv) < 5 or sys.argv[1] != "--updater-mode":
        return

    try:
        old_pid = int(sys.argv[2])
        target_exe = sys.argv[3]
        source_new_exe = sys.argv[4]

        # A. 等待主进程彻底消失 (防止文件锁)
        for _ in range(30):  # 最多等15秒
            try:
                os.kill(old_pid, 0)  # 检查PID是否还在
                time.sleep(0.5)
            except OSError:
                break

        # B. 净化环境变量：防止新进程继承旧的临时目录
        # 这一步必须在启动新程序前完成
        clean_env = os.environ.copy()
        for key in ["_MEIPASS", "PYI_EXPLORE_ROOT", "PYI_CHILD_PACKAGE"]:
            clean_env.pop(key, None)

        # C. 替换文件
        if os.path.exists(source_new_exe):
            # 先删除旧的（或者重命名）
            bak_path = target_exe + ".bak"
            if os.path.exists(bak_path):
                try:
                    os.remove(bak_path)
                except:
                    pass

            if os.path.exists(target_exe):
                os.rename(target_exe, bak_path)  # 重命名旧版

            os.rename(source_new_exe, target_exe)  # 移动新版到位

        # D. 启动新版本
        # 使用 clean_env 确保新版本重新解压 DLL
        subprocess.Popen(
            [target_exe], env=clean_env, creationflags=subprocess.DETACHED_PROCESS
        )

    except Exception as e:
        # 如果失败，记录日志或弹窗
        print("更新失败：", repr(e))
        pass
    finally:
        os._exit(0)  # 代理进程任务完成，退出


def cleanup_temp_files():
    import os
    import subprocess
    import sys

    # 1. 确定当前 EXE 的路径
    current_exe = os.path.abspath(sys.executable)
    exe_dir = os.path.dirname(current_exe)

    # 2. 定义要清理的文件名
    worker_exe = current_exe + ".worker.exe"
    bak_file = current_exe + ".bak"

    # 如果两个文件都不存在，直接返回
    if not os.path.exists(worker_exe) and not os.path.exists(bak_file):
        print(
            f"当前目录: {exe_dir}, current_exe: {current_exe}, worker_exe: {worker_exe}, bak_file: {bak_file}"
        )
        print("没有需要清理的临时文件。")
        return

    # 3. 编写一个“死循环”清理命令 (PowerShell)
    # 逻辑：循环 20 次，每次等 2 秒，尝试删除。删掉了或者超时了就退出。
    ps_cmd = f"""
        $worker = '{worker_exe}'
        $bak = '{bak_file}'
        $log = Join-Path '{exe_dir}' "cleanup_log.txt"

        "Cleanup started at $(Get-Date)" | Out-File $log

        for ($i=0; $i -lt 40; $i++) {{
            Start-Sleep -Seconds 1

            if (Test-Path -LiteralPath $worker) {{
                try {{
                    Remove-Item -LiteralPath $worker -Force -ErrorAction Stop
                    "Successfully deleted worker" | Out-File $log -Append
                }} catch {{
                    "Error deleting worker: $($_.Exception.Message)" | Out-File $log -Append
                }}
            }}

            if (Test-Path -LiteralPath $bak) {{
                try {{
                    Remove-Item -LiteralPath $bak -Force -ErrorAction Stop
                    "Successfully deleted bak" | Out-File $log -Append
                }} catch {{
                    "Error deleting bak: $($_.Exception.Message)" | Out-File $log -Append
                }}
            }}

            if (!(Test-Path -LiteralPath $worker) -and !(Test-Path -LiteralPath $bak)) {{
                "All clean!" | Out-File $log -Append
                break
            }}
        }}
        """
    # 4. 启动后台静默进程执行清理
    try:
        # 使用 CREATE_NO_WINDOW 确保用户完全看不见黑窗口
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_cmd,
            ],
            cwd=exe_dir,
            creationflags=subprocess.DETACHED_PROCESS,
        )
    except Exception as e:
        print(f"后台清理任务启动失败: {e}")


import requests
from PyQt6.QtCore import (
    QAbstractTableModel,
    QSize,
    Qt,
    QThread,
    QTimer,
    QVariant,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from libs import gs_usb

CURRENT_VERSION = "1.1.7"


def parse_version(version_text):
    nums = [int(x) for x in re.findall(r"\d+", str(version_text))]
    return tuple(nums) if nums else (0,)


def is_remote_newer(remote_version, current_version):
    remote_parts = parse_version(remote_version)
    current_parts = parse_version(current_version)
    max_len = max(len(remote_parts), len(current_parts))
    remote_parts += (0,) * (max_len - len(remote_parts))
    current_parts += (0,) * (max_len - len(current_parts))
    return remote_parts > current_parts


def show_update_detail(
    parent_window,
    title,
    text,
    detail="",
    icon=QMessageBox.Icon.Information,
):
    box = QMessageBox(parent_window)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(icon)
    if detail:
        box.setDetailedText(detail)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


#
# --- 1. DLC 与 长度的转换常量 ---
# DLC Code -> 实际字节长度
DLC_TO_LEN = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]
# 实际字节长度 -> DLC Code
LEN_TO_DLC = {
    0: 0,
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    12: 9,
    16: 10,
    20: 11,
    24: 12,
    32: 13,
    48: 14,
    64: 15,
}
# 发送可选的长度
TX_LEN_OPTIONS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]


class CanError:
    # --- Error Class (Mask) in can_id ---
    TX_TIMEOUT = 0x00000001
    LOSTARB = 0x00000002
    CRTL = 0x00000004
    PROT = 0x00000008
    TRX = 0x00000010
    ACK = 0x00000020
    BUSOFF = 0x00000040
    BUSERROR = 0x00000080
    RESTARTED = 0x00000100

    # --- Controller Status (data[1]) ---
    CTRL_MAP = {
        0x01: "RX Overflow",
        0x02: "TX Overflow",
        0x04: "RX Warning",
        0x08: "TX Warning",
        0x10: "RX Passive",
        0x20: "TX Passive",
        0x40: "Back to Active",
    }

    # --- Protocol Violation Type (data[2]) ---
    PROT_TYPE_MAP = {
        0x01: "Single Bit Error",
        0x02: "Frame Format Error",
        0x04: "Bit Stuffing Error",
        0x08: "Unable to send Dominant (Bit0)",
        0x10: "Unable to send Recessive (Bit1)",
        0x20: "Bus Overload",
        0x40: "Active Error Announcement",
        0x80: "Error on Transmission",
    }

    # --- Protocol Violation Location (data[3]) ---
    PROT_LOC_MAP = {
        0x03: "Start of Frame",
        0x02: "ID bits 28-21",
        0x06: "ID bits 20-18",
        0x04: "SRTR bit",
        0x05: "IDE bit",
        0x07: "ID bits 17-13",
        0x0F: "ID bits 12-5",
        0x0E: "ID bits 4-0",
        0x0C: "RTR bit",
        0x0D: "Reserved bit 1",
        0x09: "Reserved bit 0",
        0x0B: "DLC section",
        0x0A: "Data section",
        0x08: "CRC Sequence",
        0x18: "CRC Delimiter",
        0x19: "ACK Slot",
        0x1B: "ACK Delimiter",
        0x1A: "End of Frame",
        0x12: "Intermission",
    }

    # --- Transceiver Status (data[4]) ---
    TRX_MAP = {
        0x04: "CANH: No Wire",
        0x05: "CANH: Short to BAT",
        0x06: "CANH: Short to VCC",
        0x07: "CANH: Short to GND",
        0x40: "CANL: No Wire",
        0x50: "CANL: Short to BAT",
        0x60: "CANL: Short to VCC",
        0x70: "CANL: Short to GND",
        0x80: "CANL: Short to CANH",
    }


def check_update(parent_window):
    # 1. 访问公开仓库中的 version.json
    json_url = "https://raw.githubusercontent.com/Choosen123/LCAN-View-Release/main/version.json"

    try:
        response = requests.get(json_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        remote_version = str(data.get("version", "")).strip()
        download_url = str(data.get("url", "")).strip()
        changelog = str(data.get("changelog", "暂无更新说明"))

        if not remote_version or not download_url:
            print("更新信息格式错误: 缺少 version 或 url")
            return

        if is_remote_newer(remote_version, CURRENT_VERSION):
            reply = QMessageBox.question(
                parent_window,
                "发现新版本",
                f"当前版本: {CURRENT_VERSION}\n最新版本: {remote_version}\n\n更新内容:\n{changelog}\n\n是否立即下载更新？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                download_and_install(parent_window, download_url, remote_version)
        else:
            show_update_detail(
                parent_window,
                "检查更新",
                f"当前已是最新版本：{CURRENT_VERSION}",
            )
    except Exception as e:
        show_update_detail(
            parent_window,
            "检查更新失败",
            f"无法获取更新信息：{e}",
            traceback.format_exc(),
            QMessageBox.Icon.Warning,
        )


def is_running_as_exe():
    # 1. Nuitka 编译后的标准标识
    if "__compiled__" in globals():
        return True
    # 2. 兼容 PyInstaller 的标识
    if getattr(sys, "frozen", False):
        return True
    # 3. 兜底方案：检查 sys.executable 是否包含 python.exe
    # 如果是编译后的 EXE，sys.executable 指向的是你的 EXE 文件名
    if "python.exe" not in sys.executable.lower():
        return True

    return False


def download_and_install(parent_window, download_url, remote_version):
    if not is_running_as_exe():
        show_update_detail(
            parent_window,
            "更新提示",
            "当前为开发模式运行（python up2.py），为避免误替换 Python 解释器，已阻止自更新。",
            "请使用打包后的 EXE 版本进行在线更新。",
            QMessageBox.Icon.Warning,
        )
        return

    # 1. 下载新文件为 temp_update.exe
    progress = QProgressDialog("正在下载更新...", "取消", 0, 100, parent_window)
    progress.setWindowTitle("下载更新")
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)

    try:
        r = requests.get(download_url, stream=True, timeout=30)
        r.raise_for_status()

        base_dir = os.path.dirname(os.path.abspath(sys.executable))
        new_exe = os.path.join(base_dir, "temp_update.exe")

        total_size = int(r.headers.get("content-length", 0) or 0)
        if total_size <= 0:
            progress.setRange(0, 0)

        downloaded = 0
        with open(new_exe, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if progress.wasCanceled():
                    f.close()
                    try:
                        os.remove(new_exe)
                    except OSError:
                        pass
                    show_update_detail(
                        parent_window,
                        "更新已取消",
                        "你已取消下载，未执行更新。",
                    )
                    return

                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = int(downloaded * 100 / total_size)
                        progress.setValue(max(0, min(100, percent)))
                    QApplication.processEvents()

        progress.setValue(100)

        detail_text = (
            f"新版本: {remote_version}\n"
            f"下载地址: {download_url}\n"
            f"下载文件: {new_exe}\n\n"
            "点击“是”后将关闭当前程序并执行替换更新。"
        )
        reply = QMessageBox.question(
            parent_window,
            "下载完成",
            f"更新包已下载完成（版本 {remote_version}），是否现在安装？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            start_upgrade_script(new_exe)
        else:
            show_update_detail(
                parent_window,
                "稍后安装",
                "你选择了稍后安装，更新包已保留在程序目录。",
                detail_text,
            )
    except Exception as e:
        show_update_detail(
            parent_window,
            "下载更新失败",
            f"下载过程中发生错误：{e}",
            traceback.format_exc(),
            QMessageBox.Icon.Warning,
        )
    finally:
        progress.close()


def start_upgrade_script(new_exe_path):
    import os
    import shutil
    import subprocess
    import sys

    try:
        # 1. 准备路径
        current_exe = os.path.abspath(sys.executable)
        exe_dir = os.path.dirname(current_exe)
        # 创建一个分身，名字叫 xxx.worker.exe
        worker_exe = current_exe + ".worker.exe"

        # 2. 物理拷贝一个自己作为代理
        if os.path.exists(worker_exe):
            try:
                os.remove(worker_exe)
            except:
                pass
        shutil.copy2(current_exe, worker_exe)

        # 3. 构造参数启动代理
        # 我们告诉代理：我们的PID是多少，目标是谁，新文件在哪
        args = [
            worker_exe,
            "--updater-mode",
            str(os.getpid()),
            current_exe,
            os.path.abspath(new_exe_path),
        ]

        # 4. 启动代理进程
        # CREATE_NO_WINDOW 隐藏窗口，DETACHED_PROCESS 脱离父进程
        subprocess.Popen(
            args,
            cwd=exe_dir,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        )

        # 5. 【极其重要】立即强制退出主程序，释放所有 DLL 和文件锁
        import os

        os._exit(0)

    except Exception as e:
        print(f"启动更新代理失败: {e}")


class TraceModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # 存储原始数据 [(ts, id, len, data, is_err), ...]
        self.headers = ["Idx", "Time", "ID", "Len", "Data"]
        self.max_rows = 1000  # 缓冲区大小

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return QVariant()

        row_data = self._data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(index.row() + 1)
            if col == 1:
                return f"{row_data[0]:.4f}"
            return str(row_data[col - 1])

        # 颜色控制：如果是错误帧，整行变红
        if role == Qt.ItemDataRole.ForegroundRole and row_data[4]:
            return QColor("#e74c3c")

        return QVariant()

    def headerData(self, section, orientation, role):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return self.headers[section]
        return QVariant()

    def append_data(self, new_items):
        """批量添加数据"""
        if not new_items:
            return

        self.beginResetModel()  # 1kHz 下使用重置模型比插入行更快
        self._data.extend(new_items)
        if len(self._data) > self.max_rows:
            self._data = self._data[-self.max_rows :]
        self.endResetModel()

    def clear(self):
        if not self._data:
            return
        self.beginResetModel()
        self._data.clear()
        self.endResetModel()


# --- 2. 垂直侧边标签 (保持原有设计) ---
class VerticalLabel(QWidget):
    def __init__(self, text, bg_color="#2c3e50"):
        super().__init__()
        self.text = text
        self.bg_color = bg_color
        self.setFixedWidth(25)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(self.bg_color))
        p.setPen(Qt.GlobalColor.white)
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(-90)
        m = p.fontMetrics()
        r = m.boundingRect(self.text)
        p.drawText(int(-r.width() / 2), int(r.height() / 4), self.text)


# --- 3. 配置弹窗 (略，同前文) ---
class ConfigDialog(QDialog):
    # ... 保持之前的 scan/config 逻辑 ...
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("扫描并配置 CAN 设备")
        self.setFixedSize(500, 320)
        self.selected_dev = None
        layout = QVBoxLayout(self)
        dev_group = QGroupBox(" 可用设备")
        dev_lay = QVBoxLayout(dev_group)
        self.btn_scan = QPushButton(" 扫描设备")
        self.table_dev = QTableWidget(0, 7)
        self.table_dev.setHorizontalHeaderLabels(
            ["√", "VID", "PID", "总线", "地址", "产品名称", "序列号"]
        )
        dev_lay.addWidget(self.btn_scan)
        dev_lay.addWidget(self.table_dev)
        layout.addWidget(dev_group)
        cfg_group = QGroupBox(" CAN 配置")
        cfg_lay = QGridLayout(cfg_group)
        self.rb_fd = QRadioButton("CAN FD")
        self.rb_fd.setChecked(True)
        self.combo_nom = QComboBox()
        self.combo_nom.addItems(["1000 kbps", "250 kbps", "125 kbps", "500 kbps"])
        self.combo_data = QComboBox()
        self.combo_data.addItems(["2000 kbps", "1000 kbps", "5000 kbps"])
        cfg_lay.addWidget(QLabel("CAN 模式:"), 0, 0)
        cfg_lay.addWidget(self.rb_fd, 0, 1)
        cfg_lay.addWidget(QLabel("仲裁段:"), 1, 0)
        cfg_lay.addWidget(self.combo_nom, 1, 1)
        cfg_lay.addWidget(QLabel("数据段:"), 2, 0)
        cfg_lay.addWidget(self.combo_data, 2, 1)
        layout.addWidget(cfg_group)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.btn_scan.clicked.connect(self.scan)
        self.table_dev.itemClicked.connect(self.on_select)

    def scan(self):
        self.table_dev.setRowCount(0)
        devs = gs_usb.scan_devices()
        for d in [x for x in devs if x.is_candlelight]:
            r = self.table_dev.rowCount()
            self.table_dev.insertRow(r)
            it = QTableWidgetItem()
            it.setCheckState(Qt.CheckState.Unchecked)
            self.table_dev.setItem(r, 0, it)
            self.table_dev.setItem(r, 1, QTableWidgetItem(hex(d.vid)))
            self.table_dev.setItem(r, 5, QTableWidgetItem(d.product))
            self.table_dev.item(r, 0).setData(Qt.ItemDataRole.UserRole, (d.vid, d.pid))

    def on_select(self, it):
        for r in range(self.table_dev.rowCount()):
            self.table_dev.item(r, 0).setCheckState(Qt.CheckState.Unchecked)
        self.table_dev.item(it.row(), 0).setCheckState(Qt.CheckState.Checked)
        self.selected_dev = self.table_dev.item(it.row(), 0).data(
            Qt.ItemDataRole.UserRole
        )

    def get_config(self):
        return {
            "device": self.selected_dev,
            "nom": int(self.combo_nom.currentText().split(" ")[0]) * 1000,
            "data": int(self.combo_data.currentText().split(" ")[0]) * 1000,
            "fd": self.rb_fd.isChecked(),
        }


# --- 4. 主界面 ---
class LCANViewPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCAN-View Pro")
        self.resize(950, 500)
        self.device = None
        self.rx_map = {}
        self.tx_list = []
        self.config = None
        self.init_ui()
        self.apply_style()
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui)
        self.ui_timer.start(50)
        self.tx_timer = QTimer()
        self.tx_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.tx_timer.timeout.connect(self.process_tx)
        self.tx_timer.start(1)
        self.bus_load_timer = QTimer()
        self.bus_load_timer.timeout.connect(self.update_bus_load_ui)
        self.last_tec = 0
        self.last_rec = 0
        self.node_state = "ACTIVE"
        self.global_msg_counter = 0

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QDialog { background-color: #f5f6f7; color: #333333; }

            #ViewSelectorBar { background-color: #2c3e50; min-height: 45px; }

            QPushButton#TabButton {
                color: #bdc3c7; border: none; padding: 10px 25px; font-size: 13px;
            }
            QPushButton#TabButton[active="true"] {
                color: #ffffff; background-color: #34495e; font-weight: bold;
            }

            QTableView, QTableWidget {
                background-color: #ffffff; color: #2c3e50;
                gridline-color: #ecf0f1; border: 1px solid #dcdcdc;
                font-family: 'Consolas'; font-size: 10pt;
                selection-background-color: #3498db; selection-color: white;
            }

            /* 隔行变色效果需要在代码里开启 setAlternatingRowColors(True) */
            QTableView { alternate-background-color: #f9fbfd; }

            QHeaderView::section {
                background-color: #ebf2f9; color: #2980b9;
                padding: 6px; border: 1px solid #d6eaf8; font-weight: bold;
            }

            /* Bus Load 进度条美化 */
            QProgressBar {
                border: 1px solid #bdc3c7; background-color: #ecf0f1; border-radius: 3px; text-align: center;
            }
            QProgressBar::chunk { background-color: #3498db; width: 20px; }
        """)
        # self.setStyleSheet("""
        #     QMainWindow { background-color: #f0f0f0; }
        #     #ViewSelectorBar { background-color: #34495e; min-height: 40px; }
        #     QPushButton#TabButton { background-color: transparent; color: #ecf0f1; border: none; padding: 8px 20px; font-size: 12px; margin-top: 5px; }
        #     QPushButton#TabButton[active="true"] { background-color: #fff5d7; color: #2c3e50; font-weight: bold; border-top-left-radius: 4px; border-top-right-radius: 4px; }
        #     QTableWidget { gridline-color: #dcdcdc; font-family: 'Consolas'; font-size: 10pt; }
        #     QHeaderView::section { background-color: #f2f2f2; font-weight: bold; border: 1px solid #dcdcdc; }
        # """)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. 工具栏
        t = self.addToolBar("Main")
        act_setup = QAction(
            self.style().standardIcon(
                QApplication.style().StandardPixmap.SP_DriveNetIcon
            ),
            "Setup",
            self,
        )
        act_setup.triggered.connect(self.show_config)
        t.addAction(act_setup)
        self.act_conn = QAction(
            self.style().standardIcon(QApplication.style().StandardPixmap.SP_MediaPlay),
            "Connect",
            self,
        )
        self.act_conn.triggered.connect(self.toggle_connection)
        t.addAction(self.act_conn)
        t.addSeparator()
        act_msg = QAction(
            self.style().standardIcon(QApplication.style().StandardPixmap.SP_FileIcon),
            "New Msg",
            self,
        )
        act_msg.triggered.connect(
            lambda: self.add_tx_row(
                "123h", 1, 16, "00 11 22 33 44 55 66 77 88 99 AA BB CC DD EE FF", 100
            )
        )
        t.addAction(act_msg)
        trash_pixmap = getattr(
            QApplication.style().StandardPixmap,
            "SP_TrashIcon",
            QApplication.style().StandardPixmap.SP_DialogResetButton,
        )
        act_clear_msg = QAction(
            self.style().standardIcon(trash_pixmap),
            "Clear Msg",
            self,
        )
        act_clear_msg.triggered.connect(self.clear_messages)
        t.addAction(act_clear_msg)
        update_pixmap = getattr(
            QApplication.style().StandardPixmap,
            "SP_BrowserReload",
            QApplication.style().StandardPixmap.SP_BrowserStop,
        )
        act_check_update = QAction(
            self.style().standardIcon(update_pixmap),
            "Check Update",
            self,
        )
        act_check_update.triggered.connect(lambda: check_update(self))
        t.addAction(act_check_update)

        # 2. 标签栏 (ViewSelectorBar)
        v = QFrame()
        v.setObjectName("ViewSelectorBar")
        # --- 统一变量名为 vb_layout ---
        vb_layout = QHBoxLayout(v)
        vb_layout.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(v)

        self.btn_main = QPushButton(" Receive / Transmit")
        self.btn_main.setObjectName("TabButton")
        self.btn_trace = QPushButton(" Trace")
        self.btn_trace.setObjectName("TabButton")
        self.btn_main.setProperty("active", "true")
        self.btn_main.clicked.connect(lambda: self.switch_view(0))
        self.btn_trace.clicked.connect(lambda: self.switch_view(1))

        vb_layout.addWidget(self.btn_main)
        vb_layout.addWidget(self.btn_trace)

        # 3. 容器 (StackedWidget)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.split = QSplitter(Qt.Orientation.Vertical)

        # --- Receive Table ---
        r_w = QWidget()
        r_l = QHBoxLayout(r_w)
        r_l.setContentsMargins(0, 0, 0, 0)
        r_l.setSpacing(0)
        r_l.addWidget(VerticalLabel("RECEIVE", "#2980b9"))
        self.table_rx = QTableWidget(0, 6)
        self.table_rx.setHorizontalHeaderLabels(
            ["ID", "Type", "Length", "Data", "Cycle Time", "Count"]
        )
        self.table_rx.setWordWrap(True)
        self.table_rx.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        r_l.addWidget(self.table_rx)
        self.split.addWidget(r_w)

        # --- Transmit Table ---
        t_w = QWidget()
        t_l = QHBoxLayout(t_w)
        t_l.setContentsMargins(0, 0, 0, 0)
        t_l.setSpacing(0)
        t_l.addWidget(VerticalLabel("TRANSMIT", "#27ae60"))
        self.table_tx = QTableWidget(0, 7)
        self.table_tx.setHorizontalHeaderLabels(
            ["ID", "Type", "Length", "Data", "Cycle Time", "Count", "Comment"]
        )
        self.table_tx.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        t_l.addWidget(self.table_tx)
        self.split.addWidget(t_w)

        self.split.setSizes([500, 300])
        self.stack.addWidget(self.split)

        # --- Trace Table ---
        self.table_trace = QTableView()
        self.trace_model = TraceModel()
        self.table_trace.setModel(self.trace_model)
        self.stack.addWidget(self.table_trace)

        # 必须禁用自动列宽，这是卡顿的元凶之一！！
        self.table_trace.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.table_trace.setColumnWidth(0, 60)
        self.table_trace.setColumnWidth(1, 100)
        self.table_trace.setColumnWidth(2, 80)
        self.table_trace.setColumnWidth(3, 50)
        # self.table_trace.setColumnWidth(4, 400)
        self.table_trace.setColumnWidth(4, 1200)

        # 开启性能优化开关
        self.table_trace.verticalHeader().hide()  # 隐藏行号极大提升性能
        self.table_trace.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_trace.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )

        # 4. Bus Load (在标签栏右侧)
        # --- 将 Stretch 放在按钮和 Load 容器之间，使其靠右 ---
        vb_layout.addStretch()

        # --- Error Status 容器 (放在 Bus Load 左边) ---
        self.error_status_widget = QWidget()
        err_lay = QHBoxLayout(self.error_status_widget)
        err_lay.setContentsMargins(0, 0, 10, 0)

        # 1. 节点状态标签 (Active/Warning/Passive/Bus-Off)
        self.lbl_node_state = QLabel("IDLE")
        self.lbl_node_state.setFixedWidth(80)
        self.lbl_node_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_node_state.setStyleSheet("""
                background-color: #7f8c8d; color: white;
                border-radius: 3px; font-weight: bold; font-size: 10px;
            """)

        # 2. TEC/REC 计数器显示
        self.lbl_counters = QLabel("TEC: 0 | REC: 0")
        self.lbl_counters.setStyleSheet(
            "color: #bdc3c7; font-family: 'Consolas'; font-size: 11px;"
        )

        # 3. 最近错误描述 (简短显示)
        self.lbl_last_err = QLabel("")
        self.lbl_last_err.setStyleSheet(
            "color: #e74c3c; font-size: 11px; font-style: italic;"
        )
        self.lbl_last_err.setFixedWidth(150)  # 限制宽度

        err_lay.addWidget(self.lbl_node_state)
        err_lay.addWidget(self.lbl_counters)
        err_lay.addWidget(self.lbl_last_err)

        # 将错误状态挂件添加到 vb_layout (addStretch 之后)
        vb_layout.addWidget(self.error_status_widget)

        load_container = QWidget()
        load_lay = QHBoxLayout(load_container)
        load_lay.setContentsMargins(0, 0, 10, 0)

        lbl_load_title = QLabel("Bus Load:")
        lbl_load_title.setStyleSheet(
            "color: white; font-size: 11px; font-weight: bold;"
        )

        self.bar_bus_load = QProgressBar()
        self.bar_bus_load.setRange(0, 100)
        self.bar_bus_load.setFixedSize(120, 14)
        self.bar_bus_load.setTextVisible(False)
        self.bar_bus_load.setStyleSheet("""
                QProgressBar { border: 1px solid #555; background-color: #2c3e50; border-radius: 2px; }
                QProgressBar::chunk { background-color: #2ecc71; }
            """)

        self.lbl_load_val = QLabel("0.0%")
        self.lbl_load_val.setFixedWidth(50)
        self.lbl_load_val.setStyleSheet(
            "color: white; font-size: 11px; font-family: 'Consolas';"
        )

        load_lay.addWidget(lbl_load_title)
        load_lay.addWidget(self.bar_bus_load)
        load_lay.addWidget(self.lbl_load_val)

        # --- 确保这里使用的是 vb_layout ---
        vb_layout.addWidget(load_container)

    def update_bus_load_ui(self):
        if self.device is None:
            self.bar_bus_load.setValue(0)
            self.lbl_load_val.setText("0.0%")

            self.lbl_node_state.setText("IDLE")
            self.lbl_node_state.setStyleSheet(
                "background-color: #7f8c8d; color: white; border-radius: 3px;"
            )
            self.lbl_counters.setText("TEC: 0 | REC: 0")

            return

        try:
            hw_state = self.device.get_device_status()
            tec = hw_state.tec
            rec = hw_state.rec
            state_code = hw_state.node_state  # 0:Act, 1:Warn, 2:Pass, 3:BusOff

            # 2. 更新计数器文字
            self.lbl_counters.setText(f"TEC: {tec} | REC: {rec}")

            # 3. 更新状态标签和颜色
            # 定义状态映射
            states = {
                0: ("ACTIVE", "#27ae60"),  # 绿色
                1: ("WARNING", "#f1c40f"),  # 黄色
                2: ("PASSIVE", "#e67e22"),  # 橙色
                3: ("BUS-OFF", "#e74c3c"),  # 红色
            }

            text, color = states.get(state_code, ("UNKNOWN", "#7f8c8d"))
            self.lbl_node_state.setText(text)
            self.lbl_node_state.setStyleSheet(f"""
                    background-color: {color}; color: white;
                    border-radius: 3px; font-weight: bold;
                """)

            # 4. 自动清除机制
            # 如果回到了 ACTIVE 状态且计数器都为 0，清空具体的错误文字描述
            if state_code == 0 and tec == 0 and rec == 0:
                self.lbl_last_err.setText("")

            # 调用 C++ 绑定的 get_bus_load()
            # 假设返回的是 0-1000 的整数
            raw_val = self.device.get_bus_load()

            if raw_val >= 0:
                actual_percent = raw_val / 10.0  # 转换为 0.0 - 100.0

                # 更新文字
                self.lbl_load_val.setText(f"{actual_percent:>4.1f}%")

                # 更新进度条
                self.bar_bus_load.setValue(int(actual_percent))

                # 根据负载率动态改变颜色
                color = "#2ecc71"  # 绿色 (正常)
                if actual_percent > 80:
                    color = "#e74c3c"  # 红色 (危险)
                elif actual_percent > 50:
                    color = "#f1c40f"  # 黄色 (警告)

                self.bar_bus_load.setStyleSheet(f"""
                        QProgressBar {{ border: 1px solid #555; background-color: #2c3e50; }}
                        QProgressBar::chunk {{ background-color: {color}; }}
                    """)
        except Exception as e:
            print(f"Update Bus Load Error: {e}")

    def switch_view(self, idx):
        self.stack.setCurrentIndex(idx)
        self.btn_main.setProperty("active", "true" if idx == 0 else "false")
        self.btn_trace.setProperty("active", "true" if idx == 1 else "false")
        for b in [self.btn_main, self.btn_trace]:
            b.style().unpolish(b)
            b.style().polish(b)
            b.update()

    def show_config(self):
        dlg = ConfigDialog(self)
        # 如果当前已有配置，可以考虑传给弹窗做默认值(可选)
        if dlg.exec():
            new_config = dlg.get_config()

            # 检查是否有实质性修改，或者是否处于连接状态
            is_running = self.device is not None

            # 更新配置
            self.config = new_config

            if is_running:
                print("Configuration changed. Reconnecting...")
                self.reconnect_device()
            else:
                print("Configuration updated.")

    def reconnect_device(self):
        """自动重连序列"""
        self._do_disconnect()
        # 稍微延迟，确保上一个连接彻底关闭
        QTimer.singleShot(500, self._do_connect)

    def _do_connect(self):
        """执行实际的连接硬件逻辑"""
        try:
            vid, pid = self.config["device"]
            self.device = gs_usb.GsUsbFDCAN(vid, pid)
            self.device.setup(self.config["nom"], self.config["data"])
            self.device.start(use_fd=self.config["fd"])

            self.bus_load_timer.start(500)
            self.rx_t = ReceiveThread(self.device)
            self.rx_t.frames_signal.connect(self.on_frames)
            self.rx_t.start()

            self.act_conn.setIcon(
                self.style().standardIcon(
                    QApplication.style().StandardPixmap.SP_MediaStop
                )
            )
            print("Device connected.")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            self.device = None
            return False

    def _do_disconnect(self):
        """执行实际的断开与资源释放逻辑"""
        self.bus_load_timer.stop()
        self.bar_bus_load.setValue(0)
        self.lbl_load_val.setText("0.0%")

        # 1. 停止接收线程
        if hasattr(self, "rx_t") and self.rx_t:
            self.rx_t.running = False
            self.rx_t.wait(1000)
            self.rx_t = None

        # 2. 停止硬件并清理 C++ 对象
        if self.device:
            try:
                self.device.stop()
            except:
                pass
            self.device = None

        import gc

        gc.collect()
        time.sleep(0.4)  # 给 Windows 驱动一点释放时间

        self.act_conn.setIcon(
            self.style().standardIcon(QApplication.style().StandardPixmap.SP_MediaPlay)
        )
        print("Device disconnected.")

    def toggle_connection(self):
        if not self.device:
            if not self.config:
                self.show_config()
            if not self.config:
                return
            self._do_connect()
        else:
            self._do_disconnect()

    def insert_new_trace_row(self, timestamp, id_s, len_s, data_s, is_error=False):
        """
        统一的 Trace 行插入逻辑
        """
        self.global_msg_counter += 1
        row = self.table_trace.rowCount()

        # 限制 500 行
        MAX_ROWS = 300
        if row >= MAX_ROWS:
            self.table_trace.removeRow(0)
            row = MAX_ROWS - 1

        self.table_trace.insertRow(row)

        # 创建各项
        it_idx = QTableWidgetItem(str(self.global_msg_counter))
        it_time = QTableWidgetItem(f"{timestamp:.4f}")
        it_id = QTableWidgetItem(id_s)
        it_len = QTableWidgetItem(len_s)
        it_data = QTableWidgetItem(data_s)

        # 如果是错误帧，设置红色样式
        if is_error:
            it_id.setBackground(QColor("#e74c3c"))
            it_id.setForeground(QColor("#ffffff"))
            it_data.setForeground(QColor("#e74c3c"))
            it_len.setForeground(QColor("#e74c3c"))

        # 填入表格
        self.table_trace.setItem(row, 0, it_idx)
        self.table_trace.setItem(row, 1, it_time)
        self.table_trace.setItem(row, 2, it_id)
        self.table_trace.setItem(row, 3, it_len)
        self.table_trace.setItem(row, 4, it_data)

        # 自动滚动
        self.table_trace.scrollToBottom()

    def on_frames(self, frames):
        # 0. 初始化缓冲区 (如果不存在)
        if not hasattr(self, "temp_buffer"):
            self.temp_buffer = []
        # is_trace_visible = self.stack.currentIndex() == 1

        for f in frames:
            # --- 1. 错误帧处理逻辑 ---
            if f.get("is_error", False):
                data = f["data"]
                cid = f["can_id"]
                err_details = []

                # 解析逻辑 (保持你的原有逻辑)
                if cid & CanError.TX_TIMEOUT:
                    err_details.append("TX Timeout")
                if cid & CanError.LOSTARB:
                    err_details.append("Lost Arb")
                if cid & CanError.CRTL:
                    err_details.append("Ctrl Error")
                if cid & CanError.PROT:
                    err_details.append("Prot Error")
                if cid & CanError.TRX:
                    err_details.append("TRX Error")
                if cid & CanError.ACK:
                    err_details.append("No ACK")
                if cid & CanError.BUSOFF:
                    err_details.append("BUS-OFF")
                if cid & CanError.BUSERROR:
                    err_details.append("Bus Error")

                ctrl_status = data[1]
                for mask, msg in CanError.CTRL_MAP.items():
                    if ctrl_status & mask:
                        err_details.append(msg)

                prot_type = data[2]
                for mask, msg in CanError.PROT_TYPE_MAP.items():
                    if prot_type & mask:
                        err_details.append(msg)

                prot_loc_code = data[3]
                if prot_loc_code in CanError.PROT_LOC_MAP:
                    err_details.append(f"@{CanError.PROT_LOC_MAP[prot_loc_code]}")

                if len(data) >= 8:
                    self.last_tec, self.last_rec = data[6], data[7]

                if err_details:
                    full_msg = " | ".join(err_details)
                    self.lbl_last_err.setText(err_details[0])
                    # --- 优化：存入缓冲区 ---
                    # if is_trace_visible:
                    self.temp_buffer.append(
                        (
                            f["timestamp"],
                            "CAN ERROR",
                            f"T:{data[6]} R:{data[7]}",
                            full_msg,
                            True,
                        )
                    )

                if ctrl_status & 0x40:
                    self.lbl_last_err.setText("")
                continue

            # --- 2. 普通帧处理逻辑 ---
            cid = f["can_id"]
            current_ts = f["timestamp"]

            actual_len = DLC_TO_LEN[f["dlc"]] if f["dlc"] < 16 else len(f["data"])
            data_s = " ".join(f"{b:02X}" for b in f["data"])

            # 更新 rx_map (这部分计算很快，可以保留在循环内)
            if cid not in self.rx_map:
                r = self.table_rx.rowCount()
                self.table_rx.insertRow(r)
                for i in range(6):
                    self.table_rx.setItem(r, i, QTableWidgetItem(""))
                self.rx_map[cid] = {"row": r, "cnt": 0, "pts": current_ts, "cyc": 0}

            m = self.rx_map[cid]
            m["cnt"] += 1
            if m["cnt"] > 1:
                delta_ms = (current_ts - m["pts"]) * 1000
                if delta_ms > 0:
                    m["cyc"] = (m["cyc"] * 0.7) + (delta_ms * 0.3)

            m["pts"] = current_ts
            m["data"], m["len"], m["is_fd"] = data_s, actual_len, f["is_fd"]

            # --- 优化：存入缓冲区，不要在这里 insert_new_trace_row ---
            # if is_trace_visible:
            data_s = " ".join(f"{b:02X}" for b in f["data"])
            # 存入元组 (timestamp, id, len, data, is_error)
            self.temp_buffer.append(
                (
                    f["timestamp"],
                    f"{f['can_id']:03X}h",
                    len(f["data"]),
                    data_s,
                    f.get("is_error", False),
                )
            )

    def add_error_to_trace(self, timestamp, msg, tec, rec):
        """
        专门用于将错误帧记录到 Trace 表格中
        """
        row_count = self.table_trace.rowCount()
        # 检查最后一行是不是同一个错误

        if row_count > 0:
            last_row = row_count - 1
            last_id_item = self.table_trace.item(last_row, 2)
            last_msg_item = self.table_trace.item(last_row, 4)

            # 如果上一行也是错误，且描述相同
            if (
                last_id_item
                and last_id_item.text() == "CAN ERROR"
                and last_msg_item
                and last_msg_item.text().split(" (")[0] == msg
            ):
                # 仅更新时间、计数器
                self.table_trace.setItem(
                    last_row, 1, QTableWidgetItem(f"{timestamp:.4f}")
                )
                self.table_trace.setItem(
                    last_row, 3, QTableWidgetItem(f"T:{tec} R:{rec}")
                )
                # 可以在描述里加个次数统计，例如 "Prot Error (x150)"
                return

        # 如果是新类型的错误或第一条错误，才增加新行
        self.insert_new_trace_row(
            timestamp, "CAN ERROR", f"T:{tec} R:{rec}", msg, is_error=True
        )
        self.table_trace.scrollToBottom()

    def parse_error_frame(can_id, data):
        """
        解析错误帧并返回详细描述列表
        """
        details = []

        # 1. 解析 Error Class (can_id)
        if can_id & CanError.BUSOFF:
            details.append("【BUS OFF】节点已脱离总线")
        if can_id & CanError.ACK:
            details.append("【ACK Error】无应答(检查接线或节点数量)")
        if can_id & CanError.TX_TIMEOUT:
            details.append("【TX Timeout】发送超时")

        # 2. 解析控制器状态 (data[1])
        ctrl_status = data[1]
        for mask, desc in CanError.CTRL_MAP.items():
            if ctrl_status & mask:
                details.append(f"控制器状态: {desc}")

        # 3. 解析协议错误类型 (data[2])
        prot_type = data[2]
        for mask, desc in CanError.PROT_TYPE_MAP.items():
            if prot_type & mask:
                details.append(f"协议错误: {desc}")

        # 4. 解析错误发生位置 (data[3])
        prot_loc_code = data[3]
        if prot_loc_code in CanError.PROT_LOC_MAP:
            details.append(f"错误位置: {CanError.PROT_LOC_MAP[prot_loc_code]}")

        # 5. 解析收发器状态 (data[4])
        trx_status = data[4]
        if trx_status in CanError.TRX_MAP:
            details.append(f"物理层: {CanError.TRX_MAP[trx_status]}")

        # 6. 错误计数器 (TEC/REC)
        tec = data[6]
        rec = data[7]
        details.append(f"计数器: TEC={tec}, REC={rec}")

        return details

    def handle_error_frame(self, f):
        can_id = f["can_id"]
        data = f["data"]
        tec = data[6]
        rec = data[7]

        error_msgs = []

        # 解析 can_id 标记
        if can_id & 0x40:  # CAN_ERR_BUSOFF
            error_msgs.append("BUS-OFF")
        if can_id & 0x20:  # CAN_ERR_ACK
            error_msgs.append("ACK Error")

        # 解析 data[1] (控制器状态)
        ctrl_err = data[1]
        if ctrl_err & 0x30:
            error_msgs.append("Error Passive")
        elif ctrl_err & 0x0C:
            error_msgs.append("Error Warning")

        # 解析 data[2] (协议错误)
        prot_err = data[2]
        if prot_err & 0x01:
            error_msgs.append("Stuff Error")
        if prot_err & 0x02:
            error_msgs.append("Form Error")
        if prot_err & 0x10:
            error_msgs.append("Bit1 Error")
        if prot_err & 0x20:
            error_msgs.append("Bit0 Error")

        msg = " | ".join(error_msgs) if error_msgs else "General Error"

        # 在 Trace 表格中插入红色的行
        row = self.table_trace.rowCount()
        self.table_trace.insertRow(row)
        item_id = QTableWidgetItem("ERROR")
        item_id.setBackground(QColor("#e74c3c"))  # 红色
        self.table_trace.setItem(row, 2, item_id)
        self.table_trace.setItem(
            row, 4, QTableWidgetItem(f"{msg} (TEC:{tec}, REC:{rec})")
        )

    def update_ui(self):

        # if self.device:
        # 1. 检查底层 C++ 统计的原始接收总数
        # raw_rx_count = self.device.get_rx_count()
        # 2. 检查当前 UI 内存映射里的 ID 数量
        # map_size = len(self.rx_map)

        # 打印到控制台观察
        # print(f"Raw RX Count: {raw_rx_count}, UI Map Size: {map_size}")
        # self.status.showMessage(f"Total RX: {raw_rx_count} | IDs: {map_size}")

        for cid, m in self.rx_map.items():
            r = m["row"]
            self.table_rx.item(r, 0).setText(f"{cid:03X}h")
            self.table_rx.item(r, 1).setText("CAN FD" if m["is_fd"] else "CAN")
            self.table_rx.item(r, 2).setText(str(m["len"]))
            self.table_rx.item(r, 3).setText(m["data"])
            self.table_rx.item(r, 4).setText(f"{m['cyc']:.1f}")
            self.table_rx.item(r, 5).setText(str(m["cnt"]))
            self.table_rx.resizeRowToContents(r)

        # 刷新发送列表的计数显示
        for tx in self.tx_list:
            row = tx["row"]
            # 只在数字变化时更新，减少 CPU 消耗
            current_display = self.table_tx.item(row, 5).text()
            if current_display != str(tx["cnt"]):
                self.table_tx.item(row, 5).setText(str(tx["cnt"]))

        if self.stack.currentIndex() == 1:
            if hasattr(self, "temp_buffer") and self.temp_buffer:
                # 核心：一次性把这一秒内的几百条数据塞进模型
                self.trace_model.append_data(self.temp_buffer)
                self.temp_buffer = []  # 清空缓冲区
                self.table_trace.scrollToBottom()

    def add_tx_row(self, id_h, type_idx, len_val, data_s, cyc):
        row = self.table_tx.rowCount()
        self.table_tx.insertRow(row)
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

        cw = QWidget()
        cl = QHBoxLayout(cw)
        cl.setContentsMargins(5, 0, 5, 0)
        cb = QCheckBox()
        ed = QLineEdit(str(cyc))
        ed.setFixedWidth(40)
        cl.addWidget(cb)
        cl.addWidget(ed)
        cl.addWidget(QLabel("ms"))
        self.table_tx.setCellWidget(row, 4, cw)

        self.table_tx.setItem(row, 5, QTableWidgetItem("0"))
        self.table_tx.setItem(row, 6, QTableWidgetItem(""))

        # 绑定引用供后台处理
        self.tx_list.append(
            {
                "row": row,
                "type_cb": type_cb,
                "len_cb": len_cb,
                "cb": cb,
                "ed": ed,
                "last": 0,
                "cnt": 0,
            }
        )

    def process_tx(self):
        if not self.device:
            return

        # 获取当前高精度时间
        now_ms = time.time() * 1000

        for tx in self.tx_list:
            if tx["cb"].isChecked():
                try:
                    # 获取界面设置的周期
                    c = float(tx["ed"].text())
                    if c <= 0:
                        continue  # 周期不能为0

                    # 初始化 last 时间（如果尚未初始化）
                    if tx["last"] == 0:
                        tx["last"] = now_ms

                    # 判断是否到达发送时间点
                    if now_ms - tx["last"] >= c:
                        r = tx["row"]

                        # 1. 提取所有发送需要的参数
                        id_str = self.table_tx.item(r, 0).text().replace("h", "")
                        cid = int(id_str, 16)

                        type_str = tx["type_cb"].currentText()
                        is_fd = "CAN FD" in type_str
                        is_brs = "(BRS)" in type_str

                        target_len = int(tx["len_cb"].currentText())
                        raw_hex = self.table_tx.item(r, 3).text().replace(" ", "")
                        data_bytes = bytearray.fromhex(raw_hex)

                        # 补齐或截断数据
                        if len(data_bytes) < target_len:
                            data_bytes.extend([0] * (target_len - len(data_bytes)))
                        else:
                            data_bytes = data_bytes[:target_len]

                        # 2. 执行发送
                        if self.device.send_frame(
                            cid, bytes(data_bytes), is_fd, is_brs
                        ):
                            tx["cnt"] += 1  # 仅增加计数，不刷新 UI

                            # 3. 更新下一次发送的时间基准（采用累加法防止漂移）
                            tx["last"] += c

                            # 如果偏差太大（比如程序卡住了），强制重置同步到当前时间
                            if now_ms - tx["last"] > 1000:
                                tx["last"] = now_ms

                except Exception as e:
                    # 打印错误但不要弹窗，防止死循环
                    print(f"TX Process Error: {e}")

    def clear_messages(self):
        self.rx_map.clear()
        self.table_rx.setRowCount(0)

        for tx in self.tx_list:
            tx["cnt"] = 0
            tx["last"] = 0
            row = tx["row"]
            item = self.table_tx.item(row, 5)
            if item is not None:
                item.setText("0")

        if hasattr(self, "temp_buffer"):
            self.temp_buffer = []

        self.trace_model.clear()
        self.global_msg_counter = 0
        self.lbl_last_err.setText("")


class ReceiveThread(QThread):
    frames_signal = pyqtSignal(list)

    def __init__(self, device):
        super().__init__()
        self.device = device
        self.running = True

    def run(self):
        while self.running:
            if self.device:
                f = self.device.get_received_frames(100)
                if f:
                    self.frames_signal.emit(f)
            self.msleep(10)


def set_light_theme(app):
    # 强制使用 Fusion 样式，它对调色板的响应最准确
    app.setStyle("Fusion")

    # 创建一个浅色调色板
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(233, 231, 227))
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)

    # 应用调色板
    app.setPalette(palette)


if __name__ == "__main__":
    if "--updater-mode" in sys.argv:
        run_updater_worker()
        sys.exit(0)

    a = QApplication(sys.argv)
    set_light_theme(a)  # 应用浅色主题

    # a.setStyle("Fusion")
    w = LCANViewPro()
    w.show()

    cleanup_temp_files()
    sys.exit(a.exec())
