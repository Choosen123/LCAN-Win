#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filepath: d:\Code\pcan\up.py

import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLineEdit, QLabel, 
                             QTableWidget, QTableWidgetItem, QComboBox, 
                             QCheckBox, QGroupBox, QMessageBox, QHeaderView,
                             QSpinBox, QFileDialog, QSplitter, QTabWidget,
                             QDialog, QDialogButtonBox, QRadioButton)
from PyQt6.QtCore import QTimer, Qt, QDateTime
from PyQt6.QtGui import QFont, QColor, QAction

# ✅ 尝试加载 C++ 原生模块
try:
    import gs_usb
    print("[INFO] ✓ 使用 C++ 原生模块（高性能）")
    USE_NATIVE = True
except ImportError as e:
    print(f"[WARNING] 无法加载 C++ 模块: {e}")
    print("[INFO] 回退到 Python 实现")
    from my_gs_usb import GsUsbFDCAN
    USE_NATIVE = False

import time
from collections import defaultdict


class MessageItem:
    """消息项数据结构"""
    def __init__(self, name, can_id, data, period, enabled=False, use_fd=True, use_brs=True):
        self.name = name
        self.can_id = can_id
        self.data = data
        self.period = period
        self.enabled = enabled
        self.use_fd = use_fd
        self.use_brs = use_brs
        self.timer = None
        self.tx_count = 0


class CANStatistics:
    """CAN 统计信息"""
    def __init__(self, can_id):
        self.can_id = can_id
        self.rx_count = 0
        self.tx_count = 0
        self.last_time = 0
        self.last_data = bytes()
        self.periods = []
        self.last_rx_time = 0


class DeviceScanDialog(QDialog):
    """设备扫描对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_device = None
        self.selected_config = None
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle("扫描并配置 CAN 设备")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        
        layout = QVBoxLayout(self)
        
        # === 1. 设备列表 ===
        device_group = QGroupBox("📡 可用设备")
        device_layout = QVBoxLayout()
        
        # 工具栏
        toolbar = QHBoxLayout()
        self.btn_scan = QPushButton("🔍 扫描设备")
        self.btn_scan.clicked.connect(self.scan_devices)
        self.btn_scan.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; padding: 8px; }")
        
        self.label_device_count = QLabel("找到 0 个设备")
        toolbar.addWidget(self.btn_scan)
        toolbar.addWidget(self.label_device_count)
        toolbar.addStretch()
        
        # 设备表格
        self.device_table = QTableWidget(0, 7)
        self.device_table.setHorizontalHeaderLabels([
            "✓", "VID", "PID", "总线", "地址", "产品名称", "序列号"
        ])
        self.device_table.setColumnWidth(0, 40)
        self.device_table.setColumnWidth(1, 80)
        self.device_table.setColumnWidth(2, 80)
        self.device_table.setColumnWidth(3, 60)
        self.device_table.setColumnWidth(4, 60)
        self.device_table.setColumnWidth(5, 250)
        self.device_table.horizontalHeader().setStretchLastSection(True)
        self.device_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.device_table.itemSelectionChanged.connect(self.on_device_selected)
        
        device_layout.addLayout(toolbar)
        device_layout.addWidget(self.device_table)
        device_group.setLayout(device_layout)
        
        # === 2. 配置区 ===
        config_group = QGroupBox("⚙️ CAN 配置")
        config_layout = QVBoxLayout()
        
        # CAN 模式选择
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("CAN 模式:"))
        
        self.radio_classic = QRadioButton("经典 CAN")
        self.radio_fd = QRadioButton("CAN FD")
        self.radio_fd.setChecked(True)
        
        self.check_brs = QCheckBox("使能 BRS (位速率切换)")
        self.check_brs.setChecked(True)
        self.check_brs.setEnabled(True)
        
        self.radio_classic.toggled.connect(self.on_mode_changed)
        
        mode_row.addWidget(self.radio_classic)
        mode_row.addWidget(self.radio_fd)
        mode_row.addWidget(self.check_brs)
        mode_row.addStretch()
        
        # 仲裁段波特率
        nominal_row = QHBoxLayout()
        nominal_row.addWidget(QLabel("仲裁段波特率:"))
        
        self.combo_nominal = QComboBox()
        self.combo_nominal.addItems([
            "125 kbps",
            "250 kbps",
            "500 kbps",
            "1000 kbps (1 Mbps)"
        ])
        self.combo_nominal.setCurrentIndex(2)  # 默认 500kbps
        self.combo_nominal.setMinimumWidth(150)
        
        nominal_row.addWidget(self.combo_nominal)
        nominal_row.addStretch()
        
        # 数据段波特率
        data_row = QHBoxLayout()
        self.label_data = QLabel("数据段波特率:")
        data_row.addWidget(self.label_data)
        
        self.combo_data = QComboBox()
        self.combo_data.addItems([
            "500 kbps",
            "1000 kbps (1 Mbps)",
            "2000 kbps (2 Mbps)",
            "5000 kbps (5 Mbps)"
        ])
        self.combo_data.setCurrentIndex(2)  # 默认 2Mbps
        self.combo_data.setMinimumWidth(150)
        
        data_row.addWidget(self.combo_data)
        data_row.addStretch()
        
        # 预览
        preview_row = QHBoxLayout()
        self.label_preview = QLabel()
        self.label_preview.setStyleSheet("QLabel { color: #666; font-style: italic; }")
        self.update_preview()
        preview_row.addWidget(self.label_preview)
        preview_row.addStretch()
        
        config_layout.addLayout(mode_row)
        config_layout.addLayout(nominal_row)
        config_layout.addLayout(data_row)
        config_layout.addLayout(preview_row)
        config_group.setLayout(config_layout)
        
        # === 3. 按钮 ===
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        self.btn_ok = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.btn_ok.setText("连接设备")
        self.btn_ok.setEnabled(False)
        
        # 组装布局
        layout.addWidget(device_group)
        layout.addWidget(config_group)
        layout.addWidget(button_box)
        
        # 连接信号
        self.combo_nominal.currentIndexChanged.connect(self.update_preview)
        self.combo_data.currentIndexChanged.connect(self.update_preview)
        self.radio_fd.toggled.connect(self.update_preview)
        self.check_brs.stateChanged.connect(self.update_preview)
        
        # 自动扫描
        QTimer.singleShot(100, self.scan_devices)
    
    def scan_devices(self):
        """扫描设备"""
        self.device_table.setRowCount(0)
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("扫描中...")
        QApplication.processEvents()
        
        try:
            if USE_NATIVE:
                devices = gs_usb.scan_devices()
            else:
                # Python 实现没有扫描功能，显示默认设备
                devices = []
                QMessageBox.information(
                    self, "提示", 
                    "Python 实现不支持设备扫描。\n将使用默认 VID:0x1d50 PID:0x606f"
                )
                
                # 创建一个虚拟设备信息
                class DummyDevice:
                    def __init__(self):
                        self.vid = 0x1d50
                        self.pid = 0x606f
                        self.bus = 0
                        self.addr = 0
                        self.manufacturer = "Unknown"
                        self.product = "Candlelight (Manual)"
                        self.serial = "N/A"
                        self.is_candlelight = True
                
                devices = [DummyDevice()]
            
            # 只显示 Candlelight 设备
            candlelight_devices = [d for d in devices if d.is_candlelight]
            
            for dev in candlelight_devices:
                self.add_device_row(dev)
            
            self.label_device_count.setText(f"找到 {len(candlelight_devices)} 个 Candlelight 设备")
            
            if len(candlelight_devices) == 0:
                QMessageBox.warning(
                    self, "未找到设备",
                    "没有找到 Candlelight 设备。\n\n请检查:\n"
                    "1. 设备是否连接\n"
                    "2. 驱动是否安装 (Windows 需要 WinUSB)\n"
                    "3. 设备权限是否正确"
                )
            
        except Exception as e:
            QMessageBox.critical(self, "扫描失败", f"设备扫描失败:\n{str(e)}")
        
        finally:
            self.btn_scan.setEnabled(True)
            self.btn_scan.setText("🔍 扫描设备")
    
    def add_device_row(self, dev):
        """添加设备行"""
        row = self.device_table.rowCount()
        self.device_table.insertRow(row)
        
        # 复选框（自动选中第一个）
        chk = QCheckBox()
        if row == 0:
            chk.setChecked(True)
        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.addWidget(chk)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        self.device_table.setCellWidget(row, 0, chk_widget)
        
        # VID
        vid_item = QTableWidgetItem(f"0x{dev.vid:04X}")
        vid_item.setData(Qt.ItemDataRole.UserRole, dev)
        self.device_table.setItem(row, 1, vid_item)
        
        # PID
        self.device_table.setItem(row, 2, QTableWidgetItem(f"0x{dev.pid:04X}"))
        
        # Bus
        self.device_table.setItem(row, 3, QTableWidgetItem(str(dev.bus)))
        
        # Addr
        self.device_table.setItem(row, 4, QTableWidgetItem(str(dev.addr)))
        
        # Product
        product_item = QTableWidgetItem(dev.product or "Unknown")
        product_item.setFont(QFont("", 9, QFont.Weight.Bold))
        self.device_table.setItem(row, 5, product_item)
        
        # Serial
        self.device_table.setItem(row, 6, QTableWidgetItem(dev.serial or "N/A"))
    
    def on_device_selected(self):
        """设备选择变化"""
        selected_rows = self.device_table.selectionModel().selectedRows()
        self.btn_ok.setEnabled(len(selected_rows) > 0)
    
    def on_mode_changed(self, checked):
        """CAN 模式变化"""
        is_classic = self.radio_classic.isChecked()
        
        # 经典 CAN 禁用数据段配置
        self.label_data.setEnabled(not is_classic)
        self.combo_data.setEnabled(not is_classic)
        self.check_brs.setEnabled(not is_classic)
        
        if is_classic:
            self.check_brs.setChecked(False)
        
        self.update_preview()
    
    def update_preview(self):
        """更新配置预览"""
        is_fd = self.radio_fd.isChecked()
        use_brs = self.check_brs.isChecked()
        
        nominal_text = self.combo_nominal.currentText()
        data_text = self.combo_data.currentText()
        
        if is_fd:
            mode_str = "CAN FD"
            if use_brs:
                mode_str += " (BRS)"
            preview = f"💡 {mode_str} | 仲裁段: {nominal_text} | 数据段: {data_text}"
        else:
            preview = f"💡 经典 CAN | 波特率: {nominal_text}"
        
        self.label_preview.setText(preview)
    
    def accept(self):
        """确认"""
        # 获取选中的设备
        for row in range(self.device_table.rowCount()):
            chk_widget = self.device_table.cellWidget(row, 0)
            chk = chk_widget.findChild(QCheckBox)
            if chk and chk.isChecked():
                self.selected_device = self.device_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
                break
        
        if not self.selected_device:
            QMessageBox.warning(self, "警告", "请选择一个设备")
            return
        
        # 获取配置
        self.selected_config = {
            'use_fd': self.radio_fd.isChecked(),
            'use_brs': self.check_brs.isChecked(),
            'nominal_bitrate': self.get_bitrate_value(self.combo_nominal.currentText()),
            'data_bitrate': self.get_bitrate_value(self.combo_data.currentText())
        }
        
        super().accept()
    
    def get_bitrate_value(self, text):
        """从文本获取波特率值"""
        value_map = {
            "125 kbps": 125000,
            "250 kbps": 250000,
            "500 kbps": 500000,
            "1000 kbps (1 Mbps)": 1000000,
            "2000 kbps (2 Mbps)": 2000000,
            "5000 kbps (5 Mbps)": 5000000
        }
        return value_map.get(text, 500000)


class PCANViewDual(QMainWindow):
    def __init__(self):
        super().__init__()
        self.can_device = None
        self.is_connected = False
        self.is_paused = False
        self.message_list = []
        self.statistics = {}
        self.scroll_data = []
        self.current_config = None
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle("PCAN-View Pro - 增强版 v3.0")
        self.setGeometry(100, 100, 1600, 900)
        
        self.create_menu()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # === 1. 连接控制区 ===
        conn_group = self.create_connection_group()
        main_layout.addWidget(conn_group)
        
        # === 2. 分割器 ===
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        msg_panel = self.create_message_panel()
        splitter.addWidget(msg_panel)
        
        rx_panel = self.create_dual_view_panel()
        splitter.addWidget(rx_panel)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)
        
        self.create_statusbar()
        
        # 定时器
        self.rx_timer = QTimer()
        self.rx_timer.timeout.connect(self.receive_data)
        
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_statistics_view)
    
    def create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("文件(&F)")
        
        save_msg_action = QAction("保存消息配置(&M)", self)
        save_msg_action.triggered.connect(self.save_messages)
        file_menu.addAction(save_msg_action)
        
        load_msg_action = QAction("加载消息配置(&L)", self)
        load_msg_action.triggered.connect(self.load_messages)
        file_menu.addAction(load_msg_action)
        
        file_menu.addSeparator()
        
        save_scroll_action = QAction("导出滚动数据(&S)", self)
        save_scroll_action.setShortcut("Ctrl+S")
        save_scroll_action.triggered.connect(self.save_scroll_data)
        file_menu.addAction(save_scroll_action)
        
        save_stats_action = QAction("导出统计数据(&T)", self)
        save_stats_action.triggered.connect(self.save_statistics_data)
        file_menu.addAction(save_stats_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        help_menu = menubar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def create_connection_group(self):
        """创建连接控制组"""
        conn_group = QGroupBox("设备连接")
        conn_layout = QHBoxLayout()
        
        self.btn_connect = QPushButton("🔌 扫描并连接")
        self.btn_connect.clicked.connect(self.connect_device_with_scan)
        self.btn_connect.setStyleSheet("QPushButton { font-weight: bold; padding: 5px 15px; }")
        
        self.btn_disconnect = QPushButton("⏹ 断开")
        self.btn_disconnect.clicked.connect(self.disconnect_device)
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.setStyleSheet("QPushButton { padding: 5px 15px; }")
        
        self.label_status = QLabel("● 未连接")
        self.label_status.setStyleSheet("color: red; font-weight: bold; font-size: 12px;")
        
        self.label_device_info = QLabel("")
        self.label_device_info.setStyleSheet("color: #666; font-size: 10px;")
        
        conn_layout.addWidget(self.btn_connect)
        conn_layout.addWidget(self.btn_disconnect)
        conn_layout.addWidget(self.label_status)
        conn_layout.addWidget(self.label_device_info)
        conn_layout.addStretch()
        
        conn_group.setLayout(conn_layout)
        return conn_group
    
    def create_message_panel(self):
        """创建消息管理面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        edit_group = QGroupBox("新建/编辑消息")
        edit_layout = QVBoxLayout()
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("名称:"))
        self.edit_msg_name = QLineEdit("Message 1")
        row1.addWidget(self.edit_msg_name)
        
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("CAN ID:"))
        self.edit_msg_id = QLineEdit("0x123")
        self.edit_msg_id.setMaximumWidth(100)
        row2.addWidget(self.edit_msg_id)
        row2.addStretch()
        
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("数据:"))
        self.edit_msg_data = QLineEdit("11 22 33 44 55 66 77 88")
        row3.addWidget(self.edit_msg_data)
        
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("周期(ms):"))
        self.spin_msg_period = QSpinBox()
        self.spin_msg_period.setRange(10, 10000)
        self.spin_msg_period.setValue(100)
        self.spin_msg_period.setMaximumWidth(100)
        row4.addWidget(self.spin_msg_period)
        
        self.check_msg_fd = QCheckBox("CAN FD")
        self.check_msg_fd.setChecked(True)
        self.check_msg_brs = QCheckBox("BRS")
        self.check_msg_brs.setChecked(True)
        row4.addWidget(self.check_msg_fd)
        row4.addWidget(self.check_msg_brs)
        row4.addStretch()
        
        edit_layout.addLayout(row1)
        edit_layout.addLayout(row2)
        edit_layout.addLayout(row3)
        edit_layout.addLayout(row4)
        edit_group.setLayout(edit_layout)
        
        btn_row = QHBoxLayout()
        self.btn_add_msg = QPushButton("➕ 添加")
        self.btn_add_msg.clicked.connect(self.add_message)
        self.btn_update_msg = QPushButton("💾 更新")
        self.btn_update_msg.clicked.connect(self.update_message)
        self.btn_update_msg.setEnabled(False)
        btn_row.addWidget(self.btn_add_msg)
        btn_row.addWidget(self.btn_update_msg)
        
        list_group = QGroupBox("消息列表")
        list_layout = QVBoxLayout()
        
        self.msg_table = QTableWidget(0, 7)
        self.msg_table.setHorizontalHeaderLabels([
            "使能", "名称", "ID", "周期(ms)", "类型", "计数", "数据"
        ])
        self.msg_table.setColumnWidth(0, 50)
        self.msg_table.setColumnWidth(2, 80)
        self.msg_table.setColumnWidth(3, 80)
        self.msg_table.setColumnWidth(4, 80)
        self.msg_table.setColumnWidth(5, 60)
        self.msg_table.horizontalHeader().setStretchLastSection(True)
        self.msg_table.itemSelectionChanged.connect(self.on_message_selected)
        
        msg_btn_row = QHBoxLayout()
        self.btn_start_all = QPushButton("▶ 全部启动")
        self.btn_start_all.clicked.connect(self.start_all_messages)
        self.btn_stop_all = QPushButton("⏸ 全部停止")
        self.btn_stop_all.clicked.connect(self.stop_all_messages)
        self.btn_delete_msg = QPushButton("🗑️ 删除")
        self.btn_delete_msg.clicked.connect(self.delete_message)
        self.btn_clear_msgs = QPushButton("清空")
        self.btn_clear_msgs.clicked.connect(self.clear_messages)
        
        msg_btn_row.addWidget(self.btn_start_all)
        msg_btn_row.addWidget(self.btn_stop_all)
        msg_btn_row.addWidget(self.btn_delete_msg)
        msg_btn_row.addWidget(self.btn_clear_msgs)
        
        list_layout.addWidget(self.msg_table)
        list_layout.addLayout(msg_btn_row)
        list_group.setLayout(list_layout)
        
        layout.addWidget(edit_group)
        layout.addLayout(btn_row)
        layout.addWidget(list_group)
        
        return panel
    
    def create_dual_view_panel(self):
        """创建双视图面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        self.view_tabs = QTabWidget()
        
        stats_view = self.create_statistics_view()
        self.view_tabs.addTab(stats_view, "📊 统计视图")
        
        scroll_view = self.create_scroll_view()
        self.view_tabs.addTab(scroll_view, "📜 滚动视图")
        
        self.view_tabs.currentChanged.connect(self.on_tab_changed)
        
        layout.addWidget(self.view_tabs)
        return panel
    
    def create_statistics_view(self):
        """创建统计视图"""
        view = QWidget()
        layout = QVBoxLayout(view)
        
        toolbar = QHBoxLayout()
        self.btn_clear_stats = QPushButton("🗑️ 清空统计")
        self.btn_clear_stats.clicked.connect(self.clear_statistics_view)
        self.btn_export_stats = QPushButton("💾 导出")
        self.btn_export_stats.clicked.connect(self.save_statistics_data)
        
        self.label_stats = QLabel("总计: 0 个ID")
        self.label_stats.setStyleSheet("font-weight: bold;")
        
        toolbar.addWidget(self.btn_clear_stats)
        toolbar.addWidget(self.btn_export_stats)
        toolbar.addSpacing(20)
        toolbar.addWidget(self.label_stats)
        toolbar.addStretch()
        
        self.stats_table = QTableWidget(0, 8)
        self.stats_table.setHorizontalHeaderLabels([
            "CAN ID", "方向", "RX计数", "TX计数", "周期(ms)", "最后时间", "最后数据", "状态"
        ])
        self.stats_table.setColumnWidth(0, 100)
        self.stats_table.setColumnWidth(1, 60)
        self.stats_table.setColumnWidth(2, 80)
        self.stats_table.setColumnWidth(3, 80)
        self.stats_table.setColumnWidth(4, 80)
        self.stats_table.setColumnWidth(5, 120)
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        
        layout.addLayout(toolbar)
        layout.addWidget(self.stats_table)
        
        return view
    
    def create_scroll_view(self):
        """创建滚动视图"""
        view = QWidget()
        layout = QVBoxLayout(view)
        
        toolbar = QHBoxLayout()
        self.btn_clear_scroll = QPushButton("🗑️ 清空")
        self.btn_clear_scroll.clicked.connect(self.clear_scroll_view)
        
        self.btn_pause = QPushButton("⏸ 暂停")
        self.btn_pause.setCheckable(True)
        self.btn_pause.toggled.connect(self.toggle_pause)
        
        self.btn_export_scroll = QPushButton("💾 导出")
        self.btn_export_scroll.clicked.connect(self.save_scroll_data)
        
        self.label_scroll_rx = QLabel("RX: 0")
        self.label_scroll_tx = QLabel("TX: 0")
        self.label_scroll_total = QLabel("总计: 0")
        
        self.label_max_rows = QLabel("最大行数:")
        self.spin_max_rows = QSpinBox()
        self.spin_max_rows.setRange(100, 10000)
        self.spin_max_rows.setValue(5000)
        self.spin_max_rows.setSingleStep(100)
        self.spin_max_rows.setMaximumWidth(100)
        
        toolbar.addWidget(self.btn_clear_scroll)
        toolbar.addWidget(self.btn_pause)
        toolbar.addWidget(self.btn_export_scroll)
        toolbar.addSpacing(20)
        toolbar.addWidget(self.label_scroll_rx)
        toolbar.addWidget(self.label_scroll_tx)
        toolbar.addWidget(self.label_scroll_total)
        toolbar.addSpacing(20)
        toolbar.addWidget(self.label_max_rows)
        toolbar.addWidget(self.spin_max_rows)
        toolbar.addStretch()
        
        self.scroll_table = QTableWidget(0, 7)
        self.scroll_table.setHorizontalHeaderLabels([
            "时间", "方向", "ID", "DLC", "类型", "数据", "备注"
        ])
        self.scroll_table.setColumnWidth(0, 120)
        self.scroll_table.setColumnWidth(1, 50)
        self.scroll_table.setColumnWidth(2, 100)
        self.scroll_table.setColumnWidth(3, 50)
        self.scroll_table.setColumnWidth(4, 80)
        self.scroll_table.horizontalHeader().setStretchLastSection(True)
        
        layout.addLayout(toolbar)
        layout.addWidget(self.scroll_table)
        
        return view
    
    def create_statusbar(self):
        """创建状态栏"""
        self.statusBar().showMessage("就绪")
    
    def connect_device_with_scan(self):
        """使用扫描对话框连接设备"""
        dialog = DeviceScanDialog(self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            device = dialog.selected_device
            config = dialog.selected_config
            
            if not device or not config:
                return
            
            try:
                self.statusBar().showMessage("正在连接设备...")
                
                # 创建设备
                if USE_NATIVE:
                    self.can_device = gs_usb.GsUsbFDCAN(device.vid, device.pid)
                else:
                    self.can_device = GsUsbFDCAN(device.vid, device.pid)
                
                # 配置设备
                self.can_device.setup(
                    nominal_bitrate=config['nominal_bitrate'],
                    data_bitrate=config['data_bitrate']
                )
                
                # 启动设备
                self.can_device.start(use_fd=config['use_fd'])
                
                self.is_connected = True
                self.current_config = config
                
                self.btn_connect.setEnabled(False)
                self.btn_disconnect.setEnabled(True)
                
                self.label_status.setText("● 已连接")
                self.label_status.setStyleSheet("color: green; font-weight: bold; font-size: 12px;")
                
                # 显示设备信息
                mode_str = "CAN FD" if config['use_fd'] else "经典 CAN"
                if config['use_brs']:
                    mode_str += " (BRS)"
                
                info_text = (f"{device.product} | {mode_str} | "
                           f"仲裁段: {config['nominal_bitrate']//1000}kbps | "
                           f"数据段: {config['data_bitrate']//1000}kbps")
                self.label_device_info.setText(info_text)
                
                # 启动定时器
                self.rx_timer.start(10)
                self.stats_timer.start(500)
                
                self.statusBar().showMessage("设备连接成功!", 3000)
                QMessageBox.information(self, "成功", 
                    f"设备连接成功!\n\n"
                    f"设备: {device.product}\n"
                    f"模式: {mode_str}\n"
                    f"仲裁段: {config['nominal_bitrate']//1000} kbps\n"
                    f"数据段: {config['data_bitrate']//1000} kbps"
                )
                
            except Exception as e:
                self.statusBar().showMessage("连接失败", 3000)
                QMessageBox.critical(self, "连接错误", f"无法连接设备:\n{str(e)}")
    
    def disconnect_device(self):
        """断开设备"""
        if self.can_device:
            try:
                self.stop_all_messages()
                self.rx_timer.stop()
                self.stats_timer.stop()
                self.can_device.stop()
                self.can_device = None
            except:
                pass
        
        self.is_connected = False
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.label_status.setText("● 未连接")
        self.label_status.setStyleSheet("color: red; font-weight: bold; font-size: 12px;")
        self.label_device_info.setText("")
        self.statusBar().showMessage("设备已断开", 2000)
    
    def add_message(self):
        """添加消息"""
        try:
            name = self.edit_msg_name.text().strip()
            can_id = int(self.edit_msg_id.text(), 16)
            data_str = self.edit_msg_data.text().replace(" ", "").replace(",", "")
            data = bytes.fromhex(data_str)
            period = self.spin_msg_period.value()
            use_fd = self.check_msg_fd.isChecked()
            use_brs = self.check_msg_brs.isChecked()
            
            if not name:
                raise ValueError("请输入消息名称")
            
            if len(data) > 64:
                raise ValueError("数据长度不能超过 64 字节")
            
            msg_item = MessageItem(name, can_id, data, period, False, use_fd, use_brs)
            self.message_list.append(msg_item)
            
            self.refresh_message_table()
            
            self.statusBar().showMessage(f"消息已添加: {name}", 2000)
            
            msg_count = len(self.message_list)
            self.edit_msg_name.setText(f"Message {msg_count + 1}")
            
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))
    
    def refresh_message_table(self):
        """刷新消息列表"""
        self.msg_table.setRowCount(0)
        
        for row, msg in enumerate(self.message_list):
            self.msg_table.insertRow(row)
            
            # 使能复选框
            chk = QCheckBox()
            chk.setChecked(msg.enabled)
            chk.stateChanged.connect(lambda state, idx=row: self.toggle_message(idx, state))
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self.msg_table.setCellWidget(row, 0, chk_widget)
            
            # 名称
            name_item = QTableWidgetItem(msg.name)
            name_item.setFont(QFont("", 9, QFont.Weight.Bold))
            self.msg_table.setItem(row, 1, name_item)
            
            # ID
            self.msg_table.setItem(row, 2, QTableWidgetItem(f"0x{msg.can_id:03X}"))
            
            # 周期
            self.msg_table.setItem(row, 3, QTableWidgetItem(str(msg.period)))
            
            # 类型
            type_str = "FD" if msg.use_fd else "CAN"
            if msg.use_brs:
                type_str += "+BRS"
            self.msg_table.setItem(row, 4, QTableWidgetItem(type_str))
            
            # 计数
            count_item = QTableWidgetItem(str(msg.tx_count))
            count_item.setForeground(QColor(0, 100, 200))
            self.msg_table.setItem(row, 5, count_item)
            
            # 数据
            data_str = ' '.join(f'{b:02X}' for b in msg.data)
            data_item = QTableWidgetItem(data_str)
            data_item.setFont(QFont("Consolas", 9))
            self.msg_table.setItem(row, 6, data_item)
    
    def toggle_message(self, index, state):
        """切换消息使能"""
        if index >= len(self.message_list):
            return
        
        msg = self.message_list[index]
        enabled = (state == Qt.CheckState.Checked.value)
        
        if enabled and not self.is_connected:
            QMessageBox.warning(self, "警告", "请先连接设备!")
            self.refresh_message_table()
            return
        
        msg.enabled = enabled
        
        if enabled:
            msg.timer = QTimer()
            msg.timer.timeout.connect(lambda: self.send_message(index))
            msg.timer.start(msg.period)
            self.statusBar().showMessage(f"已启动消息: {msg.name}", 2000)
        else:
            if msg.timer:
                msg.timer.stop()
                msg.timer = None
            self.statusBar().showMessage(f"已停止消息: {msg.name}", 2000)
    
    def send_message(self, index):
        """发送消息"""
        if not self.is_connected or index >= len(self.message_list):
            return
        
        msg = self.message_list[index]
        
        try:
            success = self.can_device.send_fd_frame(msg.can_id, msg.data, msg.use_brs)
            if success:
                msg.tx_count += 1
                self.msg_table.item(index, 5).setText(str(msg.tx_count))
                
                self.update_statistics(msg.can_id, "TX", msg.data)
                self.add_scroll_row("TX", msg.can_id, len(msg.data), msg.data, 
                                  msg.use_fd, msg.use_brs, msg.name)
                
        except Exception as e:
            print(f"发送失败: {e}")
    
    def edit_message(self, index):
        """编辑消息"""
        if index >= len(self.message_list):
            return
        
        msg = self.message_list[index]
        
        self.edit_msg_name.setText(msg.name)
        self.edit_msg_id.setText(f"0x{msg.can_id:X}")
        self.edit_msg_data.setText(' '.join(f'{b:02X}' for b in msg.data))
        self.spin_msg_period.setValue(msg.period)
        self.check_msg_fd.setChecked(msg.use_fd)
        self.check_msg_brs.setChecked(msg.use_brs)
        
        self.btn_update_msg.setEnabled(True)
        self.btn_update_msg.setProperty("edit_index", index)
        
        self.msg_table.selectRow(index)
    
    def update_message(self):
        """更新消息"""
        index = self.btn_update_msg.property("edit_index")
        if index is None or index >= len(self.message_list):
            return
        
        try:
            msg = self.message_list[index]
            
            was_enabled = msg.enabled
            if was_enabled:
                self.toggle_message(index, Qt.CheckState.Unchecked.value)
            
            msg.name = self.edit_msg_name.text().strip()
            msg.can_id = int(self.edit_msg_id.text(), 16)
            data_str = self.edit_msg_data.text().replace(" ", "").replace(",", "")
            msg.data = bytes.fromhex(data_str)
            msg.period = self.spin_msg_period.value()
            msg.use_fd = self.check_msg_fd.isChecked()
            msg.use_brs = self.check_msg_brs.isChecked()
            
            self.refresh_message_table()
            
            if was_enabled:
                self.toggle_message(index, Qt.CheckState.Checked.value)
            
            self.btn_update_msg.setEnabled(False)
            self.statusBar().showMessage(f"消息已更新: {msg.name}", 2000)
            
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))
    
    def delete_message(self):
        """删除消息"""
        selected = self.msg_table.currentRow()
        if selected >= 0 and selected < len(self.message_list):
            msg = self.message_list[selected]
            if msg.enabled:
                self.toggle_message(selected, Qt.CheckState.Unchecked.value)
            
            del self.message_list[selected]
            self.refresh_message_table()
            self.statusBar().showMessage("消息已删除", 2000)
    
    def clear_messages(self):
        """清空消息"""
        reply = QMessageBox.question(self, "确认", "确定要清空所有消息吗?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.stop_all_messages()
            self.message_list.clear()
            self.refresh_message_table()
            self.statusBar().showMessage("消息已清空", 2000)
    
    def start_all_messages(self):
        """启动所有消息"""
        if not self.is_connected:
            QMessageBox.warning(self, "警告", "请先连接设备!")
            return
        
        for row in range(len(self.message_list)):
            chk_widget = self.msg_table.cellWidget(row, 0)
            chk = chk_widget.findChild(QCheckBox)
            if chk:
                chk.setChecked(True)
    
    def stop_all_messages(self):
        """停止所有消息"""
        for row in range(len(self.message_list)):
            chk_widget = self.msg_table.cellWidget(row, 0)
            chk = chk_widget.findChild(QCheckBox)
            if chk:
                chk.setChecked(False)
    
    def on_message_selected(self):
        """消息选择变化"""
        selected = self.msg_table.currentRow()
        if selected >= 0:
            self.edit_message(selected)
    
    def receive_data(self):
        """接收数据"""
        if not self.is_connected or not self.can_device:
            return
        
        try:
            frames = self.can_device.get_received_frames(100)
            
            for frame in frames:
                can_id = frame['can_id']
                data = frame['data']
                is_fd = frame['is_fd']
                is_brs = frame['is_brs']
                dlc = frame['dlc']
                
                self.update_statistics(can_id, "RX", data)
                
                if not self.is_paused:
                    self.add_scroll_row("RX", can_id, dlc, data, is_fd, is_brs)
            
        except Exception as e:
            print(f"接收错误: {e}")
    
    def update_statistics(self, can_id, direction, data):
        """更新统计信息"""
        if can_id not in self.statistics:
            self.statistics[can_id] = CANStatistics(can_id)
        
        stat = self.statistics[can_id]
        current_time = time.time()
        
        if direction == "RX":
            stat.rx_count += 1
            if stat.last_rx_time > 0:
                period = (current_time - stat.last_rx_time) * 1000
                stat.periods.append(period)
                if len(stat.periods) > 10:
                    stat.periods.pop(0)
            stat.last_rx_time = current_time
        else:
            stat.tx_count += 1
        
        stat.last_time = current_time
        stat.last_data = data
    
    def update_statistics_view(self):
        """更新统计视图表格"""
        self.stats_table.setRowCount(0)
        
        for row, (can_id, stat) in enumerate(sorted(self.statistics.items())):
            self.stats_table.insertRow(row)
            
            # ID
            id_item = QTableWidgetItem(f"0x{can_id:03X}")
            id_item.setFont(QFont("", 9, QFont.Weight.Bold))
            self.stats_table.setItem(row, 0, id_item)
            
            # 方向
            if stat.rx_count > 0 and stat.tx_count > 0:
                direction = "双向"
            elif stat.rx_count > 0:
                direction = "RX"
            else:
                direction = "TX"
            self.stats_table.setItem(row, 1, QTableWidgetItem(direction))
            
            # RX计数
            rx_item = QTableWidgetItem(str(stat.rx_count))
            rx_item.setForeground(QColor(0, 150, 0))
            self.stats_table.setItem(row, 2, rx_item)
            
            # TX计数
            tx_item = QTableWidgetItem(str(stat.tx_count))
            tx_item.setForeground(QColor(0, 100, 200))
            self.stats_table.setItem(row, 3, tx_item)
            
            # 周期
            if len(stat.periods) > 0:
                avg_period = sum(stat.periods) / len(stat.periods)
                period_str = f"{avg_period:.1f}"
            else:
                period_str = "-"
            self.stats_table.setItem(row, 4, QTableWidgetItem(period_str))
            
            # 最后时间
            if stat.last_time > 0:
                dt = QDateTime.fromSecsSinceEpoch(int(stat.last_time))
                time_str = dt.toString("hh:mm:ss.zzz")
            else:
                time_str = "-"
            self.stats_table.setItem(row, 5, QTableWidgetItem(time_str))
            
            # 最后数据
            data_str = ' '.join(f'{b:02X}' for b in stat.last_data[:8])
            if len(stat.last_data) > 8:
                data_str += "..."
            data_item = QTableWidgetItem(data_str)
            data_item.setFont(QFont("Consolas", 9))
            self.stats_table.setItem(row, 6, data_item)
            
            # 状态
            status = "活动" if (time.time() - stat.last_time) < 1.0 else "静默"
            status_item = QTableWidgetItem(status)
            if status == "活动":
                status_item.setForeground(QColor(0, 150, 0))
            else:
                status_item.setForeground(QColor(150, 150, 150))
            self.stats_table.setItem(row, 7, status_item)
        
        self.label_stats.setText(f"总计: {len(self.statistics)} 个ID")
    
    def add_scroll_row(self, direction, can_id, dlc, data, is_fd, is_brs, msg_name=""):
        """添加滚动视图行"""
        if self.scroll_table.rowCount() >= self.spin_max_rows.value():
            self.scroll_table.removeRow(0)
        
        row = self.scroll_table.rowCount()
        self.scroll_table.insertRow(row)
        
        # 时间
        now = QDateTime.currentDateTime()
        time_str = now.toString("hh:mm:ss.zzz")
        self.stats_table.setItem(row, 0, QTableWidgetItem(time_str))
        
        # 方向
        dir_item = QTableWidgetItem(direction)
        if direction == "RX":
            dir_item.setForeground(QColor(0, 150, 0))
        else:
            dir_item.setForeground(QColor(0, 100, 200))
        self.scroll_table.setItem(row, 1, dir_item)
        
        # ID
        self.scroll_table.setItem(row, 2, QTableWidgetItem(f"0x{can_id:03X}"))
        
        # DLC
        self.scroll_table.setItem(row, 3, QTableWidgetItem(str(dlc)))
        
        # 类型
        type_str = "FD" if is_fd else "CAN"
        if is_brs:
            type_str += "+BRS"
        self.scroll_table.setItem(row, 4, QTableWidgetItem(type_str))
        
        # 数据
        data_str = ' '.join(f'{b:02X}' for b in data)
        data_item = QTableWidgetItem(data_str)
        data_item.setFont(QFont("Consolas", 9))
        self.scroll_table.setItem(row, 5, data_item)
        
        # 备注
        self.scroll_table.setItem(row, 6, QTableWidgetItem(msg_name))
        
        # 自动滚动
        self.scroll_table.scrollToBottom()
        
        # 更新计数
        rx_count = sum(1 for i in range(self.scroll_table.rowCount()) 
                      if self.scroll_table.item(i, 1) and self.scroll_table.item(i, 1).text() == "RX")
        tx_count = self.scroll_table.rowCount() - rx_count
        
        self.label_scroll_rx.setText(f"RX: {rx_count}")
        self.label_scroll_tx.setText(f"TX: {tx_count}")
        self.label_scroll_total.setText(f"总计: {self.scroll_table.rowCount()}")
    
    def clear_scroll_view(self):
        """清空滚动视图"""
        self.scroll_table.setRowCount(0)
        self.label_scroll_rx.setText("RX: 0")
        self.label_scroll_tx.setText("TX: 0")
        self.label_scroll_total.setText("总计: 0")
    
    def clear_statistics_view(self):
        """清空统计视图"""
        self.statistics.clear()
        self.stats_table.setRowCount(0)
        self.label_stats.setText("总计: 0 个ID")
    
    def toggle_pause(self, checked):
        """切换暂停"""
        self.is_paused = checked
        if checked:
            self.btn_pause.setText("▶ 继续")
        else:
            self.btn_pause.setText("⏸ 暂停")
    
    def on_tab_changed(self, index):
        """标签页切换"""
        pass
    
    def save_scroll_data(self):
        """保存滚动数据"""
        if self.scroll_table.rowCount() == 0:
            QMessageBox.information(self, "提示", "没有数据可保存")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存滚动数据", "", "CSV 文件 (*.csv)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    headers = [self.scroll_table.horizontalHeaderItem(i).text() 
                             for i in range(self.scroll_table.columnCount())]
                    f.write(','.join(headers) + '\n')
                    
                    for row in range(self.scroll_table.rowCount()):
                        row_data = [self.scroll_table.item(row, col).text().replace('\n', ' ')
                                  for col in range(self.scroll_table.columnCount())]
                        f.write(','.join(row_data) + '\n')
                
                self.statusBar().showMessage(f"滚动数据已保存: {filename}", 3000)
                
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))
    
    def save_statistics_data(self):
        """保存统计数据"""
        if self.stats_table.rowCount() == 0:
            QMessageBox.information(self, "提示", "没有数据可保存")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存统计数据", "", "CSV 文件 (*.csv)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    headers = [self.stats_table.horizontalHeaderItem(i).text() 
                             for i in range(self.stats_table.columnCount())]
                    f.write(','.join(headers) + '\n')
                    
                    for row in range(self.stats_table.rowCount()):
                        row_data = [self.stats_table.item(row, col).text() 
                                  for col in range(self.stats_table.columnCount())]
                        f.write(','.join(row_data) + '\n')
                
                self.statusBar().showMessage(f"统计数据已保存: {filename}", 3000)
                
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))
    
    def save_messages(self):
        """保存消息配置"""
        if not self.message_list:
            QMessageBox.information(self, "提示", "没有消息可保存")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存消息配置", "", "JSON 文件 (*.json)"
        )
        
        if filename:
            try:
                import json
                data = []
                for msg in self.message_list:
                    data.append({
                        'name': msg.name,
                        'can_id': msg.can_id,
                        'data': msg.data.hex(),
                        'period': msg.period,
                        'use_fd': msg.use_fd,
                        'use_brs': msg.use_brs
                    })
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                
                self.statusBar().showMessage(f"消息配置已保存: {filename}", 3000)
                
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))
    
    def load_messages(self):
        """加载消息配置"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "加载消息配置", "", "JSON 文件 (*.json)"
        )
        
        if filename:
            try:
                import json
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.stop_all_messages()
                self.message_list.clear()
                
                for item in data:
                    msg = MessageItem(
                        item['name'],
                        item['can_id'],
                        bytes.fromhex(item['data']),
                        item['period'],
                        False,
                        item.get('use_fd', True),
                        item.get('use_brs', True)
                    )
                    self.message_list.append(msg)
                
                self.refresh_message_table()
                
                self.statusBar().showMessage(f"已加载 {len(self.message_list)} 条消息", 3000)
                
            except Exception as e:
                QMessageBox.critical(self, "加载失败", str(e))
    
    def show_about(self):
        """显示关于"""
        about_text = """
        <h2>PCAN-View Pro</h2>
        <p><b>版本:</b> 3.0 - 增强版</p>
        <hr>
        <p><b>主要特性:</b></p>
        <ul>
            <li>🔍 <b>设备扫描</b>: 自动扫描并列出 USB 设备</li>
            <li>⚙️ <b>灵活配置</b>: 支持经典 CAN / CAN FD 模式切换</li>
            <li>🎛️ <b>波特率可调</b>: 125k ~ 5M bps 多档位选择</li>
            <li>📊 <b>统计视图</b>: 按ID聚合，显示计数/周期/状态</li>
            <li>📜 <b>滚动视图</b>: 实时显示所有帧，可暂停</li>
            <li>✅ <b>多消息发送</b>: 独立周期，支持BRS</li>
            <li>💾 <b>数据导出</b>: CSV 格式保存</li>
            <li>⚡ <b>高性能</b>: C++ 原生模块 (可选)</li>
        </ul>
        <p><b>技术栈:</b> PyQt6 + libusb + pybind11</p>
        <p><b>作者:</b> GitHub Copilot</p>
        """
        QMessageBox.about(self, "关于", about_text)
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.is_connected:
            reply = QMessageBox.question(self, "确认退出", 
                "设备仍在连接中，确定要退出吗?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                self.disconnect_device()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    font = app.font()
    font.setPointSize(9)
    app.setFont(font)
    
    window = PCANViewDual()
    window.show()
    
    sys.exit(app.exec())