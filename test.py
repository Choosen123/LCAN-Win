import usb.core
import usb.util
import time

# 1. 寻找你的设备 (VID/PID 对应你的固件)
dev = usb.core.find(idVendor=0x1d50, idProduct=0x606f)

if dev is None:
    print("未找到 GsUsb 设备")
    exit()

print("成功找到设备，开始读取 Bus Load...")

try:
    while True:
        # 2. 发送请求 (0xC1=读, 15=你定义的请求号, 0=wValue, 0=wIndex, 2=长度)
        # 注意：如果你固件里用的是 uint16_t，这里长度设为 2
        result = dev.ctrl_transfer(0xC1, 15, 0, 0, 2)
        
        # 3. 解析数据 (小端模式)
        load_raw = int.from_bytes(result, byteorder='little')
        
        # 4. 打印结果 (假设固件放大 10 倍存储)
        print(f"\r硬件反馈原始值: {load_raw} -> 实际负载率: {load_raw/10.0:.1f}%    ", end="")
        
        time.sleep(0.5) # 每0.5秒读一次
except Exception as e:
    print(f"\n读取失败: {e}")