import usb.core
import usb.util
import struct
import threading
import time

# Request Types
GS_USB_BREQ_HOST_FORMAT = 0
GS_USB_BREQ_BITTIMING = 1
GS_USB_BREQ_MODE = 2
GS_USB_BREQ_BERR = 3
GS_USB_BREQ_BT_CONST = 4
GS_USB_BREQ_DEVICE_CONFIG = 5
GS_USB_BREQ_TIMESTAMP = 6
GS_USB_BREQ_IDENTIFY = 7
GS_USB_BREQ_GET_USER_ID = 8
GS_USB_BREQ_SET_USER_ID = 9
GS_USB_BREQ_DATA_BITTIMING = 10 
GS_USB_BREQ_BT_CONST_EXT = 11

# Mode Constants
GS_CAN_MODE_RESET = 0
GS_CAN_MODE_START = 1
GS_CAN_MODE_FD = 0x0100  # BIT(8)

# Frame Flags
GS_CAN_FLAG_FD = 0x02    # BIT(1)
GS_CAN_FLAG_BRS = 0x04   # BIT(2)

def len_to_dlc_code(length):
    """
    将实际字节长度转换为 FDCAN 的 DLC 编码值
    """
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
    else: # 64 字节
        return 15

class GsUsbFDCAN:
    def __init__(self, vid, pid):
        self.dev = usb.core.find(idVendor=vid, idProduct=pid)
        if not self.dev:
            raise Exception("Device not found")
        
        self.dev.set_configuration()
        # 获取接口号，通常为 0
        self.intf_num = 0 

    def send_control(self, request, data, value=0):
        # bmRequestType: 0x41 (Host-to-device, Vendor, Interface)
        return self.dev.ctrl_transfer(0x41, request, value, self.intf_num, data)

    def setup(self):
        # 1. 协商字节序 (Little Endian)
        self.send_control(GS_USB_BREQ_HOST_FORMAT, struct.pack("<I", 0x0000BEEF))

        # 2. 设置仲裁段位时间 (500k @ 40MHz)
        # struct gs_device_bittiming: prop_seg, phase_seg1, phase_seg2, sjw, brp
        nominal_bt = struct.pack("<IIIII", 15, 16, 8, 8, 1)
        self.send_control(GS_USB_BREQ_BITTIMING, nominal_bt, value=0)

        # 3. 设置数据段位时间 (2M @ 40MHz)
        data_bt = struct.pack("<IIIII", 9, 5, 5, 5, 1)
        # self.send_control(GS_USB_BREQ_DATA_BITTIMING, data_bt, value=0)
        self.send_control(GS_USB_BREQ_DATA_BITTIMING, data_bt, value=0)

    def start(self, use_fd=True):
        # 4. 启动设备
        # struct gs_device_mode: mode, flags
        flags = GS_CAN_MODE_FD if use_fd else 0
        mode_data = struct.pack("<II", GS_CAN_MODE_START, flags)
        self.send_control(GS_USB_BREQ_MODE, mode_data, value=0)

    def receive_loop(self):
            print("Listening...")
            while True:
                try:
                    # 0x81 为 In Endpoint
                    data = self.dev.read(0x81, 128, timeout=1000)
                    if data:
                        # 解析头 12 字节
                        echo_id, can_id, dlc, chan, flags, res = struct.unpack("<IIBBBB", data[:12])
                        
                        if echo_id == 0xffffffff: # 确认是接收到的帧
                            # data[12:12+dlc] 得到的是 array.array
                            # 使用 bytes() 强制转换一下
                            actual_data = bytes(data[12:12+dlc])
                            
                            # 解析 CAN ID (处理扩展帧标志位)
                            # gs_usb 协议中，can_id 的最高位表示是否是扩展帧等
                            clean_can_id = can_id & 0x1FFFFFFF 
                            
                            print(f"RX ID: {hex(clean_can_id)} | DLC: {dlc} | Data: {actual_data.hex(' ')}")
                    
                except usb.core.USBError as e:
                    # 忽略超时错误
                    if e.errno == 10060 or e.errno == 110 or "timeout" in str(e).lower():
                        continue
                    else:
                        print(f"USB Error: {e}")
                        break
    def send_test_frame(self, can_id, data):
        # 针对经典 CAN 帧的发送测试
        # header: echo_id, can_id, can_dlc, channel, flags, reserved
        # echo_id 传一个非 0xffffffff 的值即可，比如 0x01
        header = struct.pack("<IIBBBB", 0x01, can_id, len(data), 0, 0, 0)
        
        # 经典 CAN 负载是 8 字节，gs_usb 协议通常在 bulk 包里补齐空间
        # 这里的对齐长度取决于你固件里定义的结构体大小，通常补齐到 8 或 16
        payload = bytes(data).ljust(8, b'\x00')
        
        full_packet = header + payload
        self.dev.write(0x02, full_packet) # 0x02 为 Out 端点
        print(f"Sent ID: {hex(can_id)}")

    def send_fd_frame(self, can_id, data, use_brs=True):
            if len(data) > 64:
                raise ValueError("FDCAN 数据长度不能超过 64 字节")

            # --- 核心修改点 ---
            # 固件直接做 << 16，所以这里必须传 DLC 编码 (0-15)，不能传字节数 (0-64)
            dlc_code = len_to_dlc_code(len(data))
            # -----------------

            flags = GS_CAN_FLAG_FD
            if use_brs:
                flags |= GS_CAN_FLAG_BRS
                
            if can_id > 0x7FF:
                can_id |= 0x80000000
                
            # 注意这里的第三个参数变成了 dlc_code
            header = struct.pack("<IIBBBB", 0x00000001, can_id, dlc_code, 0, flags, 0)

            payload = bytes(data).ljust(64, b'\x00')
            full_packet = header + payload
            
            try:
                self.dev.write(0x02, full_packet, timeout=1000)
            except usb.core.USBError as e:
                print(f"发送失败: {e}")

# 在主逻辑中调用
# can.send_test_frame(0x555, [0xAA, 0xBB, 0xCC])

# 使用
can = GsUsbFDCAN(0x1d50, 0x606f) # 替换为你的 VID/PID
can.setup()
can.start()

# 启动接收线程
t = threading.Thread(target=can.receive_loop, daemon=True)
t.start()

# # 主线程循环发送
while True:
#     # # 测试发送一个 16 字节的 FD 帧
    test_data = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 
                    0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0xFF]
    
    can.send_fd_frame(0x123, test_data, use_brs=False)
#     # can.send_fd_frame(0x123, [0xAA], use_brs=False)

#     # can.send_test_frame(0x555, [0xAA, 0xBB, 0xCC])
    
    time.sleep(0.5) # 每秒发 2 帧，观察 PCAN

