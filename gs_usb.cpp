#include "gs_usb.hpp"
#include <stdexcept>
#include <iostream>
#include <cstring>

uint8_t GsUsb::LenToDlcCode(uint16_t len) {
    if(len <= 8) {
        return len;
    }else if(len <= 12){
        return 9;
    }else if(len <= 16){
        return 10;
    }else if(len <= 20) {
        return 11;
    }else if(len <= 24) {
        return 12;
    }else if(len <= 32) {
        return 13;
    }else if(len <= 48) {
        return 14;
    }else {
        return 15; // For lengths > 64, DLC is set to maximum (15)
    }
}

double GsUsb::GetTimestamp() {
    using namespace std::chrono;
    auto now = steady_clock::now();
    auto epoch = now.time_since_epoch();
    return duration_cast<duration<double>>(epoch).count();
}

GsUsb::GsUsb(uint16_t vendor_id, uint16_t product_id) {
    std::cout << "Initializing USB device..." << std::endl; 

    int ret =libusb_init(&ctx);
    if(ret < 0) {
        throw std::runtime_error("Failed to initialize libusb: " + std::string(libusb_error_name(ret)));
    }
    
    std::cout << "Opening USB device with VID: " << std::hex << vendor_id << " PID: " << std::hex << product_id << std::dec << std::endl;
    // 打开指定设备
    dev_handle = libusb_open_device_with_vid_pid(ctx, vendor_id, product_id);
    if(!dev_handle) {
        libusb_exit(ctx);
        throw std::runtime_error("Could not open USB device");
    }

    //声明接口
    ret = libusb_claim_interface(dev_handle, interface_number);
    if(ret < 0) {
        libusb_close(dev_handle);
        libusb_exit(ctx);
        throw std::runtime_error("Failed to claim interface: " + std::string(libusb_error_name(ret)));
    }

    std::cout << "USB device initialized successfully." << std::endl;
}

GsUsb::~GsUsb() {
    std::cout << "Cleaning up USB device..." << std::endl;

    Stop();
    
    if(dev_handle) {
        libusb_release_interface(dev_handle, 0);
        libusb_close(dev_handle);
    }
    if(ctx) libusb_exit(ctx);

    std::cout << "USB device cleanup completed." << std::endl;
}

int GsUsb::SendControl(uint8_t request, const uint8_t* data, uint16_t value, uint16_t length) {
    int ret = libusb_control_transfer(
        dev_handle,
        0x41, // bmRequestType: Host to device, Vendor, Interface
        request,
        value,
        interface_number,
        const_cast<uint8_t*>(data),
        length,
        2000 
    );

    if(ret < 0) {
        throw std::runtime_error("Control transfer failed: " + std::string(libusb_error_name(ret)));
    }

    std::cout << "Request=" << static_cast<int>(request) << " Value=" << value <<
    " Length=" << length << "Ret=" << ret << std::endl;

    return ret;
}

void GsUsb::Setup(uint32_t nominal_bitrate, uint32_t data_bitrate){
    std::cout << "Setting up byte orders" << std::endl;
    uint32_t byte_order = 0x0000BEEF;
    SendControl(GS_USB_BREQ_HOST_FORMAT, reinterpret_cast<uint8_t*>(&byte_order), 0, sizeof(byte_order));

    std::cout << "Setting up nominal bitrate: " << nominal_bitrate << " bps" << std::endl;
    uint32_t nominal_bt[5] = {15, 16, 8, 8, 1};
    SendControl(GS_USB_BREQ_BITTIMING, reinterpret_cast<uint8_t*>(nominal_bt), 0, sizeof(nominal_bt));

    std::cout << "Setting up data bitrate: " << data_bitrate << " bps" << std::endl;
    uint32_t data_bt[5] = {9, 5, 5, 5, 1};
    SendControl(GS_USB_BREQ_DATA_BITTIMING, reinterpret_cast<uint8_t*>(data_bt), 0, sizeof(data_bt));

    std::cout << "Setup completed." << std::endl;
}

void GsUsb::Start(bool use_fd){
    std::cout << "Starting device" << (use_fd ? " in CAN FD mode" : " in classic CAN mode") << std::endl;

    try{
        uint32_t mode_data[2] = {GS_CAN_MODE_START, 0};
        SendControl(GS_USB_BREQ_MODE, reinterpret_cast<uint8_t*>(mode_data), 0, sizeof(mode_data));
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }catch(...){
    }

    uint32_t flags = use_fd ? GS_CAN_MODE_FD : 0;
    uint32_t mode_data[2] = {GS_CAN_MODE_START, flags};
    SendControl(GS_USB_BREQ_MODE, reinterpret_cast<uint8_t*>(mode_data), 0, sizeof(mode_data));
    std::cout << "Device started successfully." << std::endl;

    stop_flag.store(false);
    rx_thread = std::thread(&GsUsb::ReceiveLoop, this);
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    if(rx_thread_running.load()){
        std::cout << "Receive thread started successfully." << std::endl;
    }else{
        std::cout << "Failed to start receive thread." << std::endl;
    }
}

void GsUsb::Stop(){
    std::cout << "Stopping device..." << std::endl;

    if(rx_thread.joinable()) {
        std::cout << "Waiting for receive thread to stop..." << std::endl;
        rx_thread.join();
        std::cout << "Receive thread stopped." << std::endl;
    }

    try{
        uint32_t mode_data[2] = {GS_CAN_MODE_RESET, 0};
        SendControl(GS_USB_BREQ_MODE, reinterpret_cast<uint8_t*>(mode_data), 0, sizeof(mode_data));
    }catch(...){
    }
    
    stop_flag.store(true);
}

void GsUsb::ReceiveLoop(){
    rx_thread_running.store(true);
    std::cout << "Receive loop started." << std::endl;

    uint16_t consecutive_errors = 0;
    uint16_t max_consecutive_errors = 10;
    uint8_t buffer[128];
    int transferred;

    while(!stop_flag.load()){
        try{
            int ret =libusb_bulk_transfer(dev_handle, 0x81, buffer, sizeof(buffer), nullptr, 100);

            if(ret == LIBUSB_ERROR_TIMEOUT){
                consecutive_errors = 0; // 超时不算错误，继续等待数据
                continue;
            }

            if(ret != 0){
                consecutive_errors++;
                std::cerr << "USB error: " << libusb_error_name(ret) << " (Consecutive errors: " << consecutive_errors << ")" << std::endl;

                if(consecutive_errors >= max_consecutive_errors){
                    std::cerr << "Too many consecutive USB errors, stopping receive loop." << std::endl;
                    break;
                }

                std::this_thread::sleep_for(std::chrono::milliseconds(100)); // 错误发生时稍作等待
                continue;
            }

            consecutive_errors = 0;

            if(transferred < 12){
                continue;
            }

            uint32_t echo_id, can_id;
            uint8_t dlc, chan, flags, reserved;

            if(sizeof(buffer) >=12){
                echo_id = *reinterpret_cast<uint32_t*>(buffer); 
                can_id = *reinterpret_cast<uint32_t*>(buffer + 4);
                dlc = buffer[8];
                chan = buffer[9];
                flags = buffer[10];
                reserved = buffer[11];

                if(echo_id == 0xFFFFFFFF){
                    // 接收帧
                    CANFrame frame;
                    frame.can_id = can_id & 0x1FFFFFFF;
                    frame.dlc = dlc;
                    frame.flags = flags;
                    frame.timestamp = GetTimestamp();
                    frame.data.assign(buffer + 12, buffer + 12 + dlc);
                
                    {
                        std::lock_guard<std::mutex> lock(rx_queue_mutex);
                        if(rx_queue.size() < MAX_QUEUE_SIZE) { // 限制队列大小，防止内存占用过高
                            rx_queue.push(frame);
                            rx_count.fetch_add(1);
                        }else{
                            std::cerr << "Receive queue full, dropping frame." << std::endl;
                        }
                    }
                }else if(echo_id == 0x00000001){
                    // 发送回显
                }else{
                    // 未知帧类型
                    std::cerr << "Unknown frame type received with echo_id: " << std::hex << echo_id << std::dec << std::endl;
                }


            }

        } catch(...) {
            std::cerr << "Error in receive loop." << std::endl;
        }
    }

    rx_thread_running.store(false);
    std::cout << "Receive loop stopped." << std::endl;

}

std::vector<CANFrame> GsUsb::GetReceivedFrames(size_t max_count){
    std::vector<CANFrame> frames;
    std::lock_guard<std::mutex> lock(rx_queue_mutex);

    while(!rx_queue.empty() && frames.size() < max_count){
            frames.push_back(rx_queue.front());
            rx_queue.pop();
    }
    return frames;
}

bool GsUsb::SendFDFrame(uint32_t can_id, const std::vector<uint8_t>& data, bool use_brs){
    uint16_t len = data.size();
    if(len > 64){
        std::cerr << "Data length exceeds maximum for CAN FD: " << len << " bytes" << std::endl;
        return false;
    }

    uint8_t dlc_code = GsUsb::LenToDlcCode(len);
    uint8_t flags = GS_CAN_FLAG_FD;
    if(use_brs){
        flags |= GS_CAN_FLAG_BRS;
    }

    if(can_id > 0x7FF){
        can_id |= 0x80000000; // 设置扩展帧标志
    }

    uint8_t packet[76] = {0};
    uint32_t echo_id = 0x00000001; // 发送帧

    std::memcpy(packet, &echo_id, 4);
    std::memcpy(packet + 4, &can_id, 4);
    packet[8] = dlc_code;
    packet[9] = 0; // channel
    packet[10] = flags;
    packet[11] = 0; // reserved
    std::memcpy(packet + 12, data.data(), len);
    std::memset(packet + 12 + len, 0, 64 - len); // 填充剩余数据为0

    int transferred;
    int ret = libusb_bulk_transfer(
        dev_handle, 
        0x02, 
        packet,
        sizeof(packet), 
        &transferred, 
        1000);

    if(ret == 0 && transferred == sizeof(packet)){
        tx_count.fetch_add(1);
        return true;
    }else{
        std::cerr << "Failed to send CAN FD frame: " << libusb_error_name(ret) << std::endl;

        if(ret == LIBUSB_ERROR_BUSY || ret == LIBUSB_ERROR_PIPE){
            std::cerr << "Buffer might be full, draining..." << std::endl;
            DrainRxBuffer();
        }

        return false;
    }


}

void GsUsb::DrainRxBuffer(){
    uint8_t buffer[128];
    int transferred;

    for(int i = 0; i < 10; ++i){ // 最多尝试10次
        int ret = libusb_bulk_transfer(dev_handle, 0x81, buffer, sizeof(buffer), &transferred, 100);
        if(ret == LIBUSB_ERROR_TIMEOUT){
            break; // 没有更多数据了
        }
    }
}


