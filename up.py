import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLineEdit, QLabel, 
                             QTableWidget, QTableWidgetItem, QComboBox, 
                             QCheckBox, QGroupBox, QMessageBox, QHeaderView,
                             QSpinBox, QFileDialog, QSplitter, QTabWidget)
from PyQt6.QtCore import QTimer, Qt, QDateTime
from PyQt6.QtGui import QFont, QColor, QAction
from my_gs_usb import GsUsbFDCAN
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
        self.last_data = b''
        self.last_time = None
        self.cycle_time_ms = 0
        self.last_rx_time = None

class PCANViewDual(QMainWindow):
    def __init__(self):
        super().__init__()
        self.can_device = None
        self.is_connected = False
        self.is_paused = False
        self.message_list = []
        self.statistics = {}  # {can_id: CANStatistics}
        self.scroll_data = []  # 滚动视图数据
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("PCAN-View Pro - 双视图模式 v2.1")
        self.setGeometry(100, 100, 1600, 900)
        
        # 创建菜单栏
        self.create_menu()
        
        # 主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # === 1. 连接控制区 ===
        conn_group = self.create_connection_group()
        main_layout.addWidget(conn_group)
        
        # === 2. 分割器：左边消息管理，右边接收视图 ===
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：发送消息管理
        msg_panel = self.create_message_panel()
        splitter.addWidget(msg_panel)
        
        # 右侧：双视图接收面板
        rx_panel = self.create_dual_view_panel()
        splitter.addWidget(rx_panel)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)
        
        # === 3. 状态栏 ===
        self.create_statusbar()
        
        # 接收定时器
        self.rx_timer = QTimer()
        self.rx_timer.timeout.connect(self.receive_data)
        
        # 统计视图更新定时器
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_statistics_view)
        
    def create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
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
        
        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")
        
        clear_scroll_action = QAction("清空滚动视图(&C)", self)
        clear_scroll_action.triggered.connect(self.clear_scroll_view)
        view_menu.addAction(clear_scroll_action)
        
        clear_stats_action = QAction("重置统计视图(&R)", self)
        clear_stats_action.triggered.connect(self.clear_statistics_view)
        view_menu.addAction(clear_stats_action)
        
        # 工具菜单
        tool_menu = menubar.addMenu("工具(&T)")
        
        stop_all_action = QAction("停止所有发送(&S)", self)
        stop_all_action.triggered.connect(self.stop_all_messages)
        tool_menu.addAction(stop_all_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def create_connection_group(self):
        """创建连接控制组"""
        conn_group = QGroupBox("设备连接")
        conn_layout = QHBoxLayout()
        
        self.label_vid = QLabel("VID:")
        self.edit_vid = QLineEdit("0x1d50")
        self.edit_vid.setMaximumWidth(80)
        
        self.label_pid = QLabel("PID:")
        self.edit_pid = QLineEdit("0x606f")
        self.edit_pid.setMaximumWidth(80)
        
        self.btn_connect = QPushButton("🔌 连接")
        self.btn_connect.clicked.connect(self.connect_device)
        self.btn_connect.setStyleSheet("QPushButton { font-weight: bold; padding: 5px 15px; }")
        
        self.btn_disconnect = QPushButton("⏹ 断开")
        self.btn_disconnect.clicked.connect(self.disconnect_device)
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.setStyleSheet("QPushButton { padding: 5px 15px; }")
        
        self.label_status = QLabel("● 未连接")
        self.label_status.setStyleSheet("color: red; font-weight: bold; font-size: 12px;")
        
        conn_layout.addWidget(self.label_vid)
        conn_layout.addWidget(self.edit_vid)
        conn_layout.addWidget(self.label_pid)
        conn_layout.addWidget(self.edit_pid)
        conn_layout.addWidget(self.btn_connect)
        conn_layout.addWidget(self.btn_disconnect)
        conn_layout.addWidget(self.label_status)
        conn_layout.addStretch()
        
        conn_group.setLayout(conn_layout)
        return conn_group
    
    def create_message_panel(self):
        """创建消息管理面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # === 消息编辑区 ===
        edit_group = QGroupBox("新建/编辑消息")
        edit_layout = QVBoxLayout()
        
        # 名称
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("名称:"))
        self.edit_msg_name = QLineEdit("Message 1")
        row1.addWidget(self.edit_msg_name)
        
        # CAN ID
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("CAN ID:"))
        self.edit_msg_id = QLineEdit("0x123")
        self.edit_msg_id.setMaximumWidth(100)
        row2.addWidget(self.edit_msg_id)
        row2.addStretch()
        
        # 数据
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("数据:"))
        self.edit_msg_data = QLineEdit("11 22 33 44 55 66 77 88")
        row3.addWidget(self.edit_msg_data)
        
        # 选项
        row4 = QHBoxLayout()
        self.check_msg_fd = QCheckBox("FD")
        self.check_msg_fd.setChecked(True)
        self.check_msg_brs = QCheckBox("BRS")
        self.check_msg_brs.setChecked(True)
        
        row4.addWidget(QLabel("周期(ms):"))
        self.spin_msg_period = QSpinBox()
        self.spin_msg_period.setRange(1, 10000)
        self.spin_msg_period.setValue(100)
        self.spin_msg_period.setMaximumWidth(80)
        
        row4.addWidget(self.spin_msg_period)
        row4.addWidget(self.check_msg_fd)
        row4.addWidget(self.check_msg_brs)
        row4.addStretch()
        
        # 按钮
        row5 = QHBoxLayout()
        self.btn_add_msg = QPushButton("➕ 添加消息")
        self.btn_add_msg.clicked.connect(self.add_message)
        self.btn_add_msg.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; padding: 8px; }")
        
        self.btn_update_msg = QPushButton("✏️ 更新消息")
        self.btn_update_msg.clicked.connect(self.update_message)
        self.btn_update_msg.setEnabled(False)
        
        row5.addWidget(self.btn_add_msg)
        row5.addWidget(self.btn_update_msg)
        
        edit_layout.addLayout(row1)
        edit_layout.addLayout(row2)
        edit_layout.addLayout(row3)
        edit_layout.addLayout(row4)
        edit_layout.addLayout(row5)
        edit_group.setLayout(edit_layout)
        
        # === 消息列表表格 ===
        list_group = QGroupBox("消息列表")
        list_layout = QVBoxLayout()
        
        # 工具栏
        toolbar = QHBoxLayout()
        self.btn_start_all = QPushButton("▶ 启动全部")
        self.btn_start_all.clicked.connect(self.start_all_messages)
        
        self.btn_stop_all = QPushButton("⏹ 停止全部")
        self.btn_stop_all.clicked.connect(self.stop_all_messages)
        
        self.btn_delete_msg = QPushButton("🗑 删除")
        self.btn_delete_msg.clicked.connect(self.delete_message)
        
        self.btn_clear_msgs = QPushButton("清空列表")
        self.btn_clear_msgs.clicked.connect(self.clear_messages)
        
        toolbar.addWidget(self.btn_start_all)
        toolbar.addWidget(self.btn_stop_all)
        toolbar.addWidget(self.btn_delete_msg)
        toolbar.addWidget(self.btn_clear_msgs)
        toolbar.addStretch()
        
        # 消息表格
        self.msg_table = QTableWidget(0, 8)
        self.msg_table.setHorizontalHeaderLabels([
            "✓", "名称", "CAN ID", "周期(ms)", "类型", "计数", "数据", "操作"
        ])
        
        header = self.msg_table.horizontalHeader()
        self.msg_table.setColumnWidth(0, 40)
        self.msg_table.setColumnWidth(1, 120)
        self.msg_table.setColumnWidth(2, 80)
        self.msg_table.setColumnWidth(3, 80)
        self.msg_table.setColumnWidth(4, 80)
        self.msg_table.setColumnWidth(5, 60)
        header.setStretchLastSection(False)
        self.msg_table.setColumnWidth(6, 300)
        self.msg_table.setColumnWidth(7, 100)
        
        self.msg_table.itemSelectionChanged.connect(self.on_message_selected)
        
        list_layout.addLayout(toolbar)
        list_layout.addWidget(self.msg_table)
        list_group.setLayout(list_layout)
        
        layout.addWidget(edit_group)
        layout.addWidget(list_group)
        
        return panel
    
    def create_dual_view_panel(self):
        """创建双视图接收面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # 创建选项卡
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        
        # === 统计视图 ===
        stats_tab = self.create_statistics_view()
        self.tab_widget.addTab(stats_tab, "📊 统计视图")
        
        # === 滚动视图 ===
        scroll_tab = self.create_scroll_view()
        self.tab_widget.addTab(scroll_tab, "📜 滚动视图")
        
        layout.addWidget(self.tab_widget)
        return panel
    
    def create_statistics_view(self):
        """创建统计视图"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        self.btn_reset_stats = QPushButton("🔄 重置统计")
        self.btn_reset_stats.clicked.connect(self.clear_statistics_view)
        
        self.btn_export_stats = QPushButton("💾 导出统计")
        self.btn_export_stats.clicked.connect(self.save_statistics_data)
        
        self.label_stats_rx = QLabel("RX: 0")
        self.label_stats_rx.setStyleSheet("color: green; font-weight: bold;")
        
        self.label_stats_tx = QLabel("TX: 0")
        self.label_stats_tx.setStyleSheet("color: blue; font-weight: bold;")
        
        self.label_unique_ids = QLabel("ID数: 0")
        
        toolbar.addWidget(self.btn_reset_stats)
        toolbar.addWidget(self.btn_export_stats)
        toolbar.addSpacing(20)
        toolbar.addWidget(self.label_stats_rx)
        toolbar.addWidget(self.label_stats_tx)
        toolbar.addWidget(self.label_unique_ids)
        toolbar.addStretch()
        
        # 统计表格
        self.stats_table = QTableWidget(0, 8)
        self.stats_table.setHorizontalHeaderLabels([
            "CAN ID", "RX计数", "TX计数", "总计", "周期(ms)", "最后时间", "最后数据", "状态"
        ])
        
        header = self.stats_table.horizontalHeader()
        self.stats_table.setColumnWidth(0, 100)
        self.stats_table.setColumnWidth(1, 80)
        self.stats_table.setColumnWidth(2, 80)
        self.stats_table.setColumnWidth(3, 80)
        self.stats_table.setColumnWidth(4, 80)
        self.stats_table.setColumnWidth(5, 130)
        header.setStretchLastSection(True)
        self.stats_table.setColumnWidth(7, 80)
        
        self.stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.setSortingEnabled(True)
        
        layout.addLayout(toolbar)
        layout.addWidget(self.stats_table)
        
        return widget
    
    def create_scroll_view(self):
        """创建滚动视图"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        self.btn_clear_scroll = QPushButton("🗑 清空")
        self.btn_clear_scroll.clicked.connect(self.clear_scroll_view)
        
        self.btn_pause = QPushButton("⏸ 暂停")
        self.btn_pause.setCheckable(True)
        self.btn_pause.clicked.connect(self.toggle_pause)
        
        self.btn_export_scroll = QPushButton("💾 导出")
        self.btn_export_scroll.clicked.connect(self.save_scroll_data)
        
        self.label_scroll_rx = QLabel("RX: 0")
        self.label_scroll_rx.setStyleSheet("color: green; font-weight: bold;")
        
        self.label_scroll_tx = QLabel("TX: 0")
        self.label_scroll_tx.setStyleSheet("color: blue; font-weight: bold;")
        
        self.label_scroll_total = QLabel("总计: 0")
        
        # 滚动速度控制
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
        
        # 滚动表格
        self.scroll_table = QTableWidget(0, 7)
        self.scroll_table.setHorizontalHeaderLabels([
            "序号", "时间", "方向", "CAN ID", "类型", "DLC", "数据"
        ])
        
        header = self.scroll_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.scroll_table.setColumnWidth(0, 60)
        self.scroll_table.setColumnWidth(1, 130)
        self.scroll_table.setColumnWidth(2, 80)
        self.scroll_table.setColumnWidth(3, 100)
        self.scroll_table.setColumnWidth(4, 80)
        self.scroll_table.setColumnWidth(5, 50)
        header.setStretchLastSection(True)
        
        self.scroll_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.scroll_table.setAlternatingRowColors(True)
        
        layout.addLayout(toolbar)
        layout.addWidget(self.scroll_table)
        
        return widget
    
    def create_statusbar(self):
        """创建状态栏"""
        self.statusBar().showMessage("就绪")
    
    def connect_device(self):
        """连接设备"""
        try:
            vid = int(self.edit_vid.text(), 16)
            pid = int(self.edit_pid.text(), 16)
            
            self.statusBar().showMessage("正在连接设备...")
            
            self.can_device = GsUsbFDCAN(vid, pid)
            self.can_device.setup()
            self.can_device.start(use_fd=True)
            
            self.is_connected = True
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            
            self.label_status.setText("● 已连接")
            self.label_status.setStyleSheet("color: green; font-weight: bold; font-size: 12px;")
            
            # 启动接收定时器
            self.rx_timer.start(10)
            
            # 启动统计更新定时器
            self.stats_timer.start(500)  # 500ms 更新一次统计视图
            
            self.statusBar().showMessage("设备连接成功!", 3000)
            QMessageBox.information(self, "成功", "设备连接成功!\n可以开始发送消息。")
            
        except Exception as e:
            self.statusBar().showMessage("连接失败", 3000)
            QMessageBox.critical(self, "连接错误", f"无法连接设备:\n{str(e)}")
    
    def disconnect_device(self):
        """断开设备"""
        self.stop_all_messages()
        
        if self.can_device:
            self.rx_timer.stop()
            self.stats_timer.stop()
            self.can_device.stop()
            self.can_device = None
        
        self.is_connected = False
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        
        self.label_status.setText("● 未连接")
        self.label_status.setStyleSheet("color: red; font-weight: bold; font-size: 12px;")
        
        self.statusBar().showMessage("设备已断开", 3000)
    
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
        
        for idx, msg in enumerate(self.message_list):
            row = self.msg_table.rowCount()
            self.msg_table.insertRow(row)
            
            # 使能复选框
            chk = QCheckBox()
            chk.setChecked(msg.enabled)
            chk.stateChanged.connect(lambda state, i=idx: self.toggle_message(i, state))
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self.msg_table.setCellWidget(row, 0, chk_widget)
            
            self.msg_table.setItem(row, 1, QTableWidgetItem(msg.name))
            self.msg_table.setItem(row, 2, QTableWidgetItem(f"0x{msg.can_id:03X}"))
            self.msg_table.setItem(row, 3, QTableWidgetItem(str(msg.period)))
            
            type_str = "FD" if msg.use_fd else "CAN"
            if msg.use_brs:
                type_str += "+BRS"
            self.msg_table.setItem(row, 4, QTableWidgetItem(type_str))
            
            count_item = QTableWidgetItem(str(msg.tx_count))
            count_item.setForeground(QColor(0, 100, 200))
            self.msg_table.setItem(row, 5, count_item)
            
            data_str = ' '.join(f'{b:02X}' for b in msg.data)
            data_item = QTableWidgetItem(data_str)
            data_item.setFont(QFont("Consolas", 9))
            self.msg_table.setItem(row, 6, data_item)
            
            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            
            btn_edit = QPushButton("编辑")
            btn_edit.setMaximumWidth(50)
            btn_edit.clicked.connect(lambda checked, i=idx: self.edit_message(i))
            
            btn_layout.addWidget(btn_edit)
            self.msg_table.setCellWidget(row, 7, btn_widget)
    
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
                
                # 更新统计
                self.update_statistics(msg.can_id, "TX", msg.data)
                
                # 添加到滚动视图
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
        current_row = self.msg_table.currentRow()
        if current_row < 0 or current_row >= len(self.message_list):
            QMessageBox.information(self, "提示", "请先选择要删除的消息")
            return
        
        msg = self.message_list[current_row]
        
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除消息 '{msg.name}' 吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if msg.timer:
                msg.timer.stop()
            
            del self.message_list[current_row]
            self.refresh_message_table()
            
            self.statusBar().showMessage("消息已删除", 2000)
    
    def clear_messages(self):
        """清空消息"""
        if not self.message_list:
            return
        
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空所有消息吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.stop_all_messages()
            self.message_list.clear()
            self.msg_table.setRowCount(0)
            self.statusBar().showMessage("消息列表已清空", 2000)
    
    def start_all_messages(self):
        """启动所有消息"""
        if not self.is_connected:
            QMessageBox.warning(self, "警告", "请先连接设备!")
            return
        
        for idx in range(len(self.message_list)):
            if not self.message_list[idx].enabled:
                self.toggle_message(idx, Qt.CheckState.Checked.value)
        
        self.refresh_message_table()
        self.statusBar().showMessage("已启动所有消息", 2000)
    
    def stop_all_messages(self):
        """停止所有消息"""
        for idx in range(len(self.message_list)):
            if self.message_list[idx].enabled:
                self.toggle_message(idx, Qt.CheckState.Unchecked.value)
        
        self.refresh_message_table()
        self.statusBar().showMessage("已停止所有消息", 2000)
    
    def on_message_selected(self):
        """消息选择变化"""
        pass
    
    def receive_data(self):
        """接收数据"""
        if not self.is_connected:
            return
        
        frames = self.can_device.get_received_frames(100)
        
        for frame in frames:
            # 更新统计
            self.update_statistics(frame['can_id'], "RX", frame['data'])
            
            # 添加到滚动视图（如果未暂停）
            if not self.is_paused:
                self.add_scroll_row(
                    "RX",
                    frame['can_id'],
                    frame['dlc'],
                    frame['data'],
                    frame['is_fd'],
                    frame['is_brs'],
                    ""
                )
    
    def update_statistics(self, can_id, direction, data):
        """更新统计信息"""
        if can_id not in self.statistics:
            self.statistics[can_id] = CANStatistics(can_id)
        
        stat = self.statistics[can_id]
        current_time = time.time()
        
        if direction == "RX":
            stat.rx_count += 1
            
            # 计算周期时间
            if stat.last_rx_time:
                cycle_ms = (current_time - stat.last_rx_time) * 1000
                stat.cycle_time_ms = int(cycle_ms)
            
            stat.last_rx_time = current_time
            
        elif direction == "TX":
            stat.tx_count += 1
        
        stat.last_data = data
        stat.last_time = current_time
    
    def update_statistics_view(self):
        """更新统计视图表格"""
        # 保存当前排序状态
        was_sorting_enabled = self.stats_table.isSortingEnabled()
        self.stats_table.setSortingEnabled(False)
        
        # 更新或添加行
        existing_rows = {}
        for row in range(self.stats_table.rowCount()):
            can_id_text = self.stats_table.item(row, 0).text()
            can_id = int(can_id_text, 16)
            existing_rows[can_id] = row
        
        for can_id, stat in self.statistics.items():
            if can_id in existing_rows:
                row = existing_rows[can_id]
            else:
                row = self.stats_table.rowCount()
                self.stats_table.insertRow(row)
                
                # CAN ID
                id_item = QTableWidgetItem(f"0x{can_id:03X}")
                id_item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                self.stats_table.setItem(row, 0, id_item)
            
            # RX计数
            rx_item = QTableWidgetItem(str(stat.rx_count))
            rx_item.setForeground(QColor(0, 150, 0))
            self.stats_table.setItem(row, 1, rx_item)
            
            # TX计数
            tx_item = QTableWidgetItem(str(stat.tx_count))
            tx_item.setForeground(QColor(0, 0, 200))
            self.stats_table.setItem(row, 2, tx_item)
            
            # 总计
            total = stat.rx_count + stat.tx_count
            self.stats_table.setItem(row, 3, QTableWidgetItem(str(total)))
            
            # 周期
            if stat.cycle_time_ms > 0:
                self.stats_table.setItem(row, 4, QTableWidgetItem(f"{stat.cycle_time_ms}"))
            else:
                self.stats_table.setItem(row, 4, QTableWidgetItem("-"))
            
            # 最后时间
            if stat.last_time:
                time_str = QDateTime.fromSecsSinceEpoch(int(stat.last_time)).toString("HH:mm:ss")
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
        
        # 更新统计标签
        total_rx = sum(s.rx_count for s in self.statistics.values())
        total_tx = sum(s.tx_count for s in self.statistics.values())
        
        self.label_stats_rx.setText(f"RX: {total_rx}")
        self.label_stats_tx.setText(f"TX: {total_tx}")
        self.label_unique_ids.setText(f"ID数: {len(self.statistics)}")
        
        # 恢复排序
        self.stats_table.setSortingEnabled(was_sorting_enabled)
    
    def add_scroll_row(self, direction, can_id, dlc, data, is_fd, is_brs, msg_name=""):
        """添加滚动视图行"""
        row = self.scroll_table.rowCount()
        self.scroll_table.insertRow(row)
        
        # 序号
        self.scroll_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        
        # 时间
        time_str = QDateTime.currentDateTime().toString("HH:mm:ss.zzz")
        self.scroll_table.setItem(row, 1, QTableWidgetItem(time_str))
        
        # 方向
        dir_text = direction
        if msg_name:
            dir_text += f"\n({msg_name})"
        
        dir_item = QTableWidgetItem(dir_text)
        if direction == "RX":
            dir_item.setForeground(QColor(0, 150, 0))
            dir_item.setBackground(QColor(230, 255, 230))
        else:
            dir_item.setForeground(QColor(0, 0, 200))
            dir_item.setBackground(QColor(230, 240, 255))
        self.scroll_table.setItem(row, 2, dir_item)
        
        # CAN ID
        id_item = QTableWidgetItem(f"0x{can_id:03X}")
        id_item.setFont(QFont("Consolas", 9))
        self.scroll_table.setItem(row, 3, id_item)
        
        # 类型
        type_str = "FD" if is_fd else "CAN"
        if is_brs:
            type_str += "+BRS"
        type_item = QTableWidgetItem(type_str)
        type_item.setForeground(QColor(255, 140, 0) if is_fd else QColor(100, 100, 100))
        self.scroll_table.setItem(row, 4, type_item)
        
        # DLC
        self.scroll_table.setItem(row, 5, QTableWidgetItem(str(dlc)))
        
        # 数据
        data_str = ' '.join(f'{b:02X}' for b in data)
        data_item = QTableWidgetItem(data_str)
        data_item.setFont(QFont("Consolas", 9))
        self.scroll_table.setItem(row, 6, data_item)
        
        # 自动滚动
        if not self.is_paused:
            self.scroll_table.scrollToBottom()
        
        # 更新标签
        rx_count = sum(1 for r in range(self.scroll_table.rowCount()) 
                      if self.scroll_table.item(r, 2).text().startswith("RX"))
        tx_count = self.scroll_table.rowCount() - rx_count
        
        self.label_scroll_rx.setText(f"RX: {rx_count}")
        self.label_scroll_tx.setText(f"TX: {tx_count}")
        self.label_scroll_total.setText(f"总计: {self.scroll_table.rowCount()}")
        
        # 限制最大行数
        max_rows = self.spin_max_rows.value()
        while self.scroll_table.rowCount() > max_rows:
            self.scroll_table.removeRow(0)
    
    def clear_scroll_view(self):
        """清空滚动视图"""
        reply = QMessageBox.question(
            self, "确认", "确定要清空滚动视图吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.scroll_table.setRowCount(0)
            self.label_scroll_rx.setText("RX: 0")
            self.label_scroll_tx.setText("TX: 0")
            self.label_scroll_total.setText("总计: 0")
            self.statusBar().showMessage("滚动视图已清空", 2000)
    
    def clear_statistics_view(self):
        """清空统计视图"""
        reply = QMessageBox.question(
            self, "确认", "确定要重置统计数据吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.statistics.clear()
            self.stats_table.setRowCount(0)
            self.label_stats_rx.setText("RX: 0")
            self.label_stats_tx.setText("TX: 0")
            self.label_unique_ids.setText("ID数: 0")
            self.statusBar().showMessage("统计数据已重置", 2000)
    
    def toggle_pause(self, checked):
        """切换暂停"""
        self.is_paused = checked
        if checked:
            self.btn_pause.setText("▶ 继续")
            self.statusBar().showMessage("滚动视图已暂停")
        else:
            self.btn_pause.setText("⏸ 暂停")
            self.statusBar().showMessage("滚动视图已继续")
    
    def on_tab_changed(self, index):
        """标签页切换"""
        if index == 0:
            self.statusBar().showMessage("切换到统计视图", 1000)
        else:
            self.statusBar().showMessage("切换到滚动视图", 1000)
    
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
        <p><b>版本:</b> 2.1 - 双视图模式</p>
        <hr>
        <p><b>主要特性:</b></p>
        <ul>
            <li>📊 <b>统计视图</b>: 按ID聚合，显示计数/周期/状态</li>
            <li>📜 <b>滚动视图</b>: 实时显示所有帧，可暂停</li>
            <li>✅ 多消息独立周期发送</li>
            <li>💾 配置保存/加载</li>
            <li>📤 数据导出 (CSV)</li>
            <li>🔄 CAN FD + BRS 支持</li>
        </ul>
        <p><b>技术栈:</b> PyQt6 + PyUSB</p>
        """
        QMessageBox.about(self, "关于", about_text)
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.is_connected or any(msg.enabled for msg in self.message_list):
            reply = QMessageBox.question(
                self, "确认退出", 
                "设备仍在连接或有消息正在发送，确定要退出吗?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_all_messages()
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