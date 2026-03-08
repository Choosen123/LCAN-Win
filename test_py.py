#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filepath: d:\Code\pcan\test_python.py

import sys
import time

# 导入 C++ 实现的模块
import gs_usb

def test_basic():
    """基础功能测试"""
    print("=" * 60)
    print("基础功能测试")
    print("=" * 60)
    
    try:
        # 1. 创建设备
        print("\n1. 创建设备...")
        can = gs_usb.GsUsbFDCAN(0x1d50, 0x606f)
        print(f"   ✓ 设备创建成功: {can}")
        
        # 2. 配置
        print("\n2. 配置设备...")
        can.setup(nominal_bitrate=500000, data_bitrate=2000000)
        print("   ✓ 配置完成")
        
        # 3. 启动
        print("\n3. 启动设备...")
        can.start(use_fd=True)
        print("   ✓ 设备已启动")
        time.sleep(0.5)
        
        # 4. 发送测试
        print("\n4. 发送测试...")
        for i in range(5):
            data = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88])
            success = can.send_fd_frame(0x123, data, use_brs=True)
            print(f"   发送帧 #{i+1}: {'✓' if success else '✗'}")
            time.sleep(0.1)
        
        # 5. 接收测试
        print("\n5. 接收测试...")
        time.sleep(0.5)
        frames = can.get_received_frames(max_count=100)
        print(f"   接收到 {len(frames)} 个帧")
        
        for i, frame in enumerate(frames[:3]):  # 只显示前3个
            print(f"\n   帧 #{i+1}:")
            print(f"     CAN ID:    0x{frame['can_id']:03X}")
            print(f"     DLC:       {frame['dlc']}")
            print(f"     FD:        {frame['is_fd']}")
            print(f"     BRS:       {frame['is_brs']}")
            print(f"     Data:      {frame['data'].hex(' ')}")
            print(f"     Timestamp: {frame['timestamp']:.6f}")
        
        if len(frames) > 3:
            print(f"   ... 还有 {len(frames) - 3} 个帧")
        
        # 6. 统计信息
        print("\n6. 统计信息:")
        print(f"   RX 计数: {can.get_rx_count()}")
        print(f"   TX 计数: {can.get_tx_count()}")
        print(f"   RX 线程: {'运行中' if can.is_rx_thread_running() else '已停止'}")
        
        # 7. 停止
        print("\n7. 停止设备...")
        can.stop()
        print("   ✓ 设备已停止")
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_performance():
    """性能测试"""
    print("\n" + "=" * 60)
    print("性能测试")
    print("=" * 60)
    
    try:
        can = gs_usb.GsUsbFDCAN(0x1d50, 0x606f)
        can.setup()
        can.start(use_fd=True)
        
        # 发送性能测试
        print("\n发送性能测试 (1000 帧)...")
        data = bytes([0xAA] * 32)
        
        start_time = time.time()
        success_count = 0
        
        for i in range(1000):
            if can.send_fd_frame(0x100 + (i % 256), data, use_brs=True):
                success_count += 1
        
        elapsed = time.time() - start_time
        
        print(f"  耗时: {elapsed:.3f} 秒")
        print(f"  成功: {success_count} / 1000")
        print(f"  速率: {success_count / elapsed:.1f} 帧/秒")
        
        # 接收性能测试
        time.sleep(1)
        print("\n接收性能测试...")
        
        start_time = time.time()
        frames = can.get_received_frames(max_count=10000)
        elapsed = time.time() - start_time
        
        print(f"  接收: {len(frames)} 个帧")
        print(f"  耗时: {elapsed * 1000:.1f} 毫秒")
        if len(frames) > 0:
            print(f"  速率: {len(frames) / elapsed:.1f} 帧/秒")
        
        can.stop()
        
        print("\n✓ 性能测试完成")
        return True
        
    except Exception as e:
        print(f"\n✗ 性能测试失败: {e}")
        return False

def test_compatibility():
    """兼容性测试（与原 Python 实现对比）"""
    print("\n" + "=" * 60)
    print("兼容性测试")
    print("=" * 60)
    
    # 测试接口是否与原 my_gs_usb.py 兼容
    required_methods = [
        'send_fd_frame',
        'get_received_frames',
        'setup',
        'start',
        'stop',
        'get_rx_count',
        'get_tx_count',
    ]
    
    can_class = gs_usb.GsUsbFDCAN
    
    print("\n检查必需方法:")
    all_ok = True
    for method in required_methods:
        has_method = hasattr(can_class, method)
        status = "✓" if has_method else "✗"
        print(f"  {status} {method}")
        if not has_method:
            all_ok = False
    
    if all_ok:
        print("\n✓ 接口兼容")
    else:
        print("\n✗ 接口不兼容")
    
    return all_ok

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("GS_USB Python 模块测试套件")
    print("=" * 60)
    
    results = []
    
    # 运行测试
    results.append(("基础功能", test_basic()))
    results.append(("兼容性", test_compatibility()))
    
    # 可选：性能测试（需要设备连接）
    if input("\n是否运行性能测试？(y/n): ").lower() == 'y':
        results.append(("性能", test_performance()))
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ 所有测试通过！")
        print("\n可以直接替换 my_gs_usb.py 使用:")
        print("  # from my_gs_usb import GsUsbFDCAN")
        print("  from gs_usb import GsUsbFDCAN")
    else:
        print("✗ 部分测试失败")
    print("=" * 60)
    
    sys.exit(0 if all_passed else 1)