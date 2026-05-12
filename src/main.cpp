#include "gs_usb.hpp"
#include <iostream>
#include <iomanip>

void print_frame(const CANFrame& frame){
    std::cout << "[Rx] ID=0x" << std::hex << std::setw(3) << std::setfill('0') << frame.can_id << std::dec 
              << " DLC=" << static_cast<int>(frame.dlc) 
              << " FD=" << frame.is_fd()              
              << " BRS=" << frame.is_brs()
              << " Data=";
    for(uint8_t byte : frame.data){
        std::cout << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(byte) << " ";
    }
    std::cout << std::dec << std::endl;
}

int main(){
   std::cout << "=== GS_USB Test Program ===" << std::endl;
    
    try {
        // 1. 创建设备
        GsUsb can(0x1d50, 0x606f);
        
        // 2. 配置
        can.Setup(1000000, 2000000);
        
        // 3. 启动
        can.Start(true);
        
        std::cout << "\n=== Starting test loop ===" << std::endl;
        std::cout << "Press Ctrl+C to exit\n" << std::endl;
        
        // 4. 测试循环
        for (int i = 0; i < 100; ++i) {
            // 发送测试帧
            std::vector<uint8_t> data = {0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88};
            
            bool success = can.SendFrame(0x123, data, true);
            if (success) {
                std::cout << "[TX] Sent frame " << (i + 1) << std::endl;
            } else {
                std::cerr << "[TX] Failed to send frame " << (i + 1) << std::endl;
            }
            
            // 接收帧
            auto frames = can.GetReceivedFrames(100);
            for (const auto& frame : frames) {
                print_frame(frame);
            }
            
            // 等待
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        
        // 5. 显示统计
        std::cout << "\n=== Statistics ===" << std::endl;
        std::cout << "RX Count: " << can.GetRxCount() << std::endl;
        std::cout << "TX Count: " << can.GetTxCount() << std::endl;
        std::cout << "RX Thread Running: " << (can.IsRxThreadRunning() ? "Yes" : "No") << std::endl;
        
        // 6. 停止
        can.Stop();
        
        std::cout << "\n=== Test completed ===" << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}