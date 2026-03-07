import usb.core
import usb.util
import struct
import threading
import time
from queue import Queue, Empty
import traceback

# Request Types
GS_USB_BREQ_HOST_FORMAT = 0
GS_USB_BREQ_BITTIMING = 1
GS_USB_BREQ_MODE = 2
GS_USB_BREQ_DATA_BITTIMING = 10
GS_USB_BREQ_BERR = 9

# Mode Constants
GS_CAN_MODE_START = 1
GS_CAN_MODE_RESET = 0
GS_CAN_MODE_FD = 0x0100

# Frame Flags
GS_CAN_FLAG_FD = 0x02
GS_CAN_FLAG_BRS = 0x04

def len_to_dlc_code(length):
    """将实际字节长度转换为 FDCAN 的 DLC 编码值"""
    if length <= 8:
        return length
    elif length <= 12:
        return 9
    elif length <= 16:
        return 10
    elif length <= 20:
        return 11
    elif length <= 24:
        return 12
    elif length <= 32:
        return 13
    elif length <= 48:
        return 14
    else:
        return 15

class GsUsbFDCAN:
    def __init__(self, vid, pid):
        print(f"[INIT] 查找设备 VID=0x{vid:04X}, PID=0x{pid:04X}")
        self.dev = usb.core.find(idVendor=vid, idProduct=pid)
        if not self.dev:
            raise Exception("Device not found")
        
        print(f"[INIT] 设备找到: {self.dev}")
        
        try:
            # 重置设备
            self.dev.reset()
            time.sleep(0.5)
        except:
            pass
        
        # 设置配置
        try:
            self.dev.set_configuration()
        except usb.core.USBError as e:
            print(f"[WARN] 设置配置失败: {e}")
        
        self.intf_num = 0
        
        # 尝试分离内核驱动
        try:
            if self.dev.is_kernel_driver_active(self.intf_num):
                print("[INIT] 分离内核驱动")
                self.dev.detach_kernel_driver(self.intf_num)
        except:
            pass
        
        # 声明接口
        try:
            usb.util.claim_interface(self.dev, self.intf_num)
            print("[INIT] 声明接口成功")
        except usb.core.USBError as e:
            print(f"[WARN] 声明接口失败: {e}")
        
        self.rx_queue = Queue(maxsize=10000)
        self.rx_thread = None
        self.stop_flag = threading.Event()
        self.rx_count = 0
        self.tx_count = 0
        self.rx_thread_running = False

    def send_control(self, request, data, value=0):
        """发送控制传输"""
        try:
            ret = self.dev.ctrl_transfer(0x41, request, value, self.intf_num, data, timeout=2000)
            print(f"[CTRL] Request={request}, Value={value}, Ret={ret}")
            return ret
        except usb.core.USBError as e:
            print(f"[ERROR] 控制传输失败: {e}")
            raise

    def setup(self, nominal_bitrate=500000, data_bitrate=2000000):
        """设置波特率"""
        print("[SETUP] 开始配置设备")
        
        # 1. 协商字节序
        print("[SETUP] 设置字节序")
        self.send_control(GS_USB_BREQ_HOST_FORMAT, struct.pack("<I", 0x0000BEEF))

        # 2. 设置仲裁段位时间 (500kbps @ 40MHz)
        print("[SETUP] 设置仲裁段位时间 (500kbps)")
        nominal_bt = struct.pack("<IIIII", 15, 16, 8, 8, 1)
        self.send_control(GS_USB_BREQ_BITTIMING, nominal_bt, value=0)

        # 3. 设置数据段位时间 (2Mbps @ 40MHz)
        print("[SETUP] 设置数据段位时间 (2Mbps)")
        data_bt = struct.pack("<IIIII", 9, 5, 5, 5, 1)
        self.send_control(GS_USB_BREQ_DATA_BITTIMING, data_bt, value=0)
        
        print("[SETUP] 配置完成")

    def start(self, use_fd=True):
        """启动 CAN 设备"""
        print(f"[START] 启动设备 (FD={use_fd})")
        
        # 先停止
        try:
            mode_data = struct.pack("<II", GS_CAN_MODE_RESET, 0)
            self.send_control(GS_USB_BREQ_MODE, mode_data, value=0)
            time.sleep(0.1)
        except:
            pass
        
        # 启动设备
        flags = GS_CAN_MODE_FD if use_fd else 0
        mode_data = struct.pack("<II", GS_CAN_MODE_START, flags)
        self.send_control(GS_USB_BREQ_MODE, mode_data, value=0)
        
        print("[START] 设备已启动")
        
        # 启动接收线程
        self.stop_flag.clear()
        self.rx_thread_running = False
        self.rx_thread = threading.Thread(target=self._receive_loop, daemon=True, name="RX-Thread")
        self.rx_thread.start()
        
        # 等待线程启动
        time.sleep(0.2)
        if self.rx_thread_running:
            print("[START] ✓ 接收线程已启动")
        else:
            print("[START] ✗ 警告：接收线程可能未正常启动")

    def stop(self):
        """停止设备"""
        print("[STOP] 停止设备")
        
        # 停止接收线程
        self.stop_flag.set()
        if self.rx_thread and self.rx_thread.is_alive():
            print("[STOP] 等待接收线程退出...")
            self.rx_thread.join(timeout=2)
            if self.rx_thread.is_alive():
                print("[STOP] 警告：接收线程未能正常退出")
            else:
                print("[STOP] 接收线程已退出")
        
        # 停止设备
        try:
            mode_data = struct.pack("<II", GS_CAN_MODE_RESET, 0)
            self.send_control(GS_USB_BREQ_MODE, mode_data, value=0)
        except:
            pass
        
        self.rx_thread_running = False

    def _receive_loop(self):
        """接收线程 - 增强版"""
        print("[RX-THREAD] 接收线程启动")
        self.rx_thread_running = True
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while not self.stop_flag.is_set():
            try:
                # 从 USB 读取数据 (端点 0x81)
                data = self.dev.read(0x81, 128, timeout=100)
                
                # 重置错误计数
                consecutive_errors = 0
                
                if data and len(data) >= 12:
                    # 解析帧头
                    echo_id, can_id, dlc, chan, flags, res = struct.unpack("<IIBBBB", data[:12])
                    
                    # 判断是接收帧还是发送回显
                    if echo_id == 0xffffffff:
                        # ✓ 这是接收到的帧
                        actual_data = bytes(data[12:12+dlc])
                        clean_can_id = can_id & 0x1FFFFFFF
                        
                        frame = {
                            'timestamp': time.time(),
                            'can_id': clean_can_id,
                            'dlc': dlc,
                            'flags': flags,
                            'data': actual_data,
                            'is_fd': bool(flags & GS_CAN_FLAG_FD),
                            'is_brs': bool(flags & GS_CAN_FLAG_BRS)
                        }
                        
                        try:
                            self.rx_queue.put_nowait(frame)
                            self.rx_count += 1
                        except:
                            pass  # 队列满，丢弃
                    
                    elif echo_id == 0x00000001:
                        # ✓ 这是发送回显（TX Echo）
                        # 重要：必须读取并丢弃，否则缓冲区会满
                        # print(f"[TX-ECHO] CAN ID=0x{can_id:X}")
                        pass
                    
                    else:
                        # 未知帧类型
                        print(f"[RX-THREAD] 未知帧类型: echo_id=0x{echo_id:08X}")
                
            except usb.core.USBError as e:
                error_str = str(e).lower()
                
                if "timeout" in error_str or "timed out" in error_str:
                    # 超时是正常的，继续
                    consecutive_errors = 0
                    continue
                
                elif "no such device" in error_str or "device not found" in error_str:
                    # 设备断开
                    print(f"[RX-THREAD] 设备断开: {e}")
                    break
                
                else:
                    # 其他错误
                    consecutive_errors += 1
                    print(f"[RX-THREAD] USB 错误 ({consecutive_errors}/{max_consecutive_errors}): {e}")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        print("[RX-THREAD] 连续错误过多，退出线程")
                        break
                    
                    time.sleep(0.1)
            
            except Exception as e:
                consecutive_errors += 1
                print(f"[RX-THREAD] 未知错误: {e}")
                traceback.print_exc()
                
                if consecutive_errors >= max_consecutive_errors:
                    break
                
                time.sleep(0.1)
        
        self.rx_thread_running = False
        print("[RX-THREAD] 接收线程退出")

    def get_received_frames(self, max_count=100):
        """获取接收到的帧"""
        frames = []
        while len(frames) < max_count:
            try:
                frames.append(self.rx_queue.get_nowait())
            except Empty:
                break
        return frames

    def send_fd_frame(self, can_id, data, use_brs=True):
        """发送 FDCAN 帧"""
        if len(data) > 64:
            raise ValueError("FDCAN 数据长度不能超过 64 字节")

        dlc_code = len_to_dlc_code(len(data))
        flags = GS_CAN_FLAG_FD
        if use_brs:
            flags |= GS_CAN_FLAG_BRS
            
        # 扩展帧标志
        if can_id > 0x7FF:
            can_id |= 0x80000000
            
        # 构造帧
        header = struct.pack("<IIBBBB", 0x00000001, can_id, dlc_code, 0, flags, 0)
        payload = bytes(data).ljust(64, b'\x00')
        full_packet = header + payload
        
        try:
            # 写入端点 0x02
            self.dev.write(0x02, full_packet, timeout=1000)
            self.tx_count += 1
            return True
        
        except usb.core.USBError as e:
            print(f"[TX-ERROR] 发送失败: {e}")
            
            # 如果是缓冲区满，尝试清空接收缓冲区
            if "resource busy" in str(e).lower() or "pipe" in str(e).lower():
                print("[TX-ERROR] 缓冲区可能已满，尝试清空...")
                self._drain_rx_buffer()
            
            return False

    def _drain_rx_buffer(self):
        """清空接收缓冲区"""
        try:
            for _ in range(10):
                try:
                    self.dev.read(0x81, 128, timeout=10)
                except:
                    break
        except:
            pass
    
    def is_rx_thread_alive(self):
        """检查接收线程是否存活"""
        return self.rx_thread_running and self.rx_thread and self.rx_thread.is_alive()