#include "gs_usb.hpp"
#include <stdexcept>
#include <iostream>
#include <cstring>

// 根据CAN FD规范，DLC编码与实际数据长度的映射关系如下：
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

// 根据CAN FD规范，DLC编码与实际数据长度的映射关系如下：
uint8_t GsUsb::DlcCodeToLen(uint8_t dlc_code) {
    if(dlc_code <= 8) {
        return dlc_code;
    }else if(dlc_code == 9){
        return 12;
    }else if(dlc_code == 10){
        return 16;
    }else if(dlc_code == 11) {
        return 20;
    }else if(dlc_code == 12) {
        return 24;
    }else if(dlc_code == 13) {
        return 32;
    }else if(dlc_code == 14) {
        return 48;
    }else {
        return 64; // For DLC code of 15, length is set to maximum (64)
    }
}

// 获取时间戳
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
    
    // 开启调试日志（可选）
    // libusb_set_option(ctx, LIBUSB_OPTION_LOG_LEVEL, LIBUSB_LOG_LEVEL_DEBUG);
    
    std::cout << "Opening USB device with VID: " << std::hex << vendor_id << " PID: " << std::hex << product_id << std::dec << std::endl;
    // 打开指定设备
    dev_handle = libusb_open_device_with_vid_pid(ctx, vendor_id, product_id);
    if(!dev_handle) {
        libusb_exit(ctx);
        throw std::runtime_error("Could not open USB device");
    }

    libusb_reset_device(dev_handle);

    libusb_set_auto_detach_kernel_driver(dev_handle, 1);
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
        libusb_reset_device(dev_handle); 
        libusb_release_interface(dev_handle, 0);
        libusb_close(dev_handle);

        dev_handle = nullptr;
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
    BitTimingConfig nominal_config = CalculateBitTiming(nominal_bitrate);
    uint32_t nominal_bt[5] = {nominal_config.prop_seg, nominal_config.phase_seg1, nominal_config.phase_seg2, nominal_config.sjw, nominal_config.brp};
    SendControl(GS_USB_BREQ_BITTIMING, reinterpret_cast<uint8_t*>(nominal_bt), 0, sizeof(nominal_bt));

    std::cout << "Setting up data bitrate: " << data_bitrate << " bps" << std::endl;
    BitTimingConfig data_config = CalculateBitTiming(data_bitrate);
    uint32_t data_bt[5] = {data_config.prop_seg, data_config.phase_seg1, data_config.phase_seg2, data_config.sjw, data_config.brp};
    SendControl(GS_USB_BREQ_DATA_BITTIMING, reinterpret_cast<uint8_t*>(data_bt), 0, sizeof(data_bt));

    std::cout << "Setup completed." << std::endl;
}

void GsUsb::Start(bool use_fd){
    std::cout << "Starting device" << (use_fd ? " in CAN FD mode" : " in classic CAN mode") << std::endl;

    try{
        uint32_t mode_data[2] = {GS_CAN_MODE_RESET, 0};
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

    stop_flag.store(true);

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
            int ret =libusb_bulk_transfer(
                        dev_handle,
                        0x81,
                        buffer, 
                        sizeof(buffer), 
                        &transferred,
                        100);

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
                    if(can_id & CAN_ERR_FLAG){
                        std::cerr << "Error frame received with CAN ID: " << std::hex << can_id << std::dec << std::endl;
                    
                        // 错误帧
                        CANFrame error_frame;
                        error_frame.can_id = can_id & 0x1FFFFFFF;
                        error_frame.dlc = dlc;
                        error_frame.flags = flags;
                        error_frame.timestamp = GetTimestamp();
                        error_frame.data.assign(buffer + 12, buffer + 12 + DlcCodeToLen(dlc));
                        error_frame.is_error = true;

                        {
                            std::lock_guard<std::mutex> lock(rx_queue_mutex);
                            if(rx_queue.size() < MAX_QUEUE_SIZE) { // 限制队列大小，防止内存占用过高
                                rx_queue.push(error_frame);
                                rx_count.fetch_add(1);
                            }else{
                                std::cerr << "Receive queue full, dropping error frame." << std::endl;
                            }
                        }

                    }else{
                        // 接收帧
                        CANFrame frame;
                        frame.can_id = can_id & 0x1FFFFFFF;
                        frame.dlc = dlc;
                        frame.flags = flags;
                        frame.timestamp = GetTimestamp();
                        frame.data.assign(buffer + 12, buffer + 12 + DlcCodeToLen(dlc));
                    
                        {
                            std::lock_guard<std::mutex> lock(rx_queue_mutex);
                            if(rx_queue.size() < MAX_QUEUE_SIZE) { // 限制队列大小，防止内存占用过高
                                rx_queue.push(frame);
                                rx_count.fetch_add(1);
                            }else{
                                std::cerr << "Receive queue full, dropping frame." << std::endl;
                            }
                        }
                    }
                }else{
                    // 发送回显
                    std::cout << "Echo TX for CAN ID: " << std::hex << can_id << std::dec << " DLC: " << static_cast<int>(dlc) << " Flags: " << static_cast<int>(flags) << std::endl;
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

bool GsUsb::SendFrame(uint32_t can_id, const std::vector<uint8_t>& data, bool use_fd, bool use_brs){
    uint16_t len = data.size();
    uint8_t flags = 0;
    int packet_size = 0;
    uint8_t dlc_code = GsUsb::LenToDlcCode(len);

    if(use_fd){
        if(len > 64){
            std::cerr << "Data length exceeds maximum for CAN FD: " << len << " bytes" << std::endl;
            return false;
        }
        dlc_code = GsUsb::LenToDlcCode(len);
        flags |= GS_CAN_FLAG_FD;
        if(use_brs){
            flags |= GS_CAN_FLAG_BRS;
        }
        packet_size = 76;
    }else{
        if(len > 8){
            std::cerr << "Data length exceeds maximum for classic CAN: " << len << " bytes" << std::endl;
            return false;
        }
        dlc_code = GsUsb::LenToDlcCode(len);
        flags = 0; 
        packet_size = 20; // 12字节头 + 8字节数据
    }

    if(can_id > 0x7FF){
        can_id |= 0x80000000; // 设置扩展帧标志
    }

    std::vector<uint8_t> packet(packet_size, 0); 
    uint32_t echo_id = 0x00000001; // 发送帧

    std::memcpy(packet.data(), &echo_id, 4);
    std::memcpy(packet.data() + 4, &can_id, 4);
    packet[8] = dlc_code;
    packet[9] = 0; // channel
    packet[10] = flags;
    packet[11] = 0; // reserved
    std::memcpy(packet.data() + 12, data.data(), len);

    int transferred;
    int ret = libusb_bulk_transfer(
        dev_handle, 
        0x02, 
        packet.data(),
        packet.size(), 
        &transferred, 
        1000);

    if(ret == 0 && transferred == packet_size){
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

std::vector<USBDeviceInfo> GsUsb::ScanDevices(){
    std::vector<USBDeviceInfo> devices;

    libusb_context* scan_ctx = nullptr;
    int ret = libusb_init(&scan_ctx);
    if(ret < 0) {
        std::cerr << "Failed to initialize libusb for scanning: " << libusb_error_name(ret) << std::endl;
        return devices;
    }

    libusb_device **devs;
    libusb_device *found = NULL;
    ssize_t cnt = libusb_get_device_list(NULL, &devs);
    ssize_t i = 0;

    if (cnt < 0){
        std::cerr << "Failed to get device list: " << libusb_error_name(cnt) << std::endl;
        libusb_exit(scan_ctx);
        return devices;
    }
    
    for (i = 0; i < cnt; i++) {
        libusb_device *device = devs[i];
        libusb_device_descriptor desc;
        if(libusb_get_device_descriptor(device, &desc) == 0){
            USBDeviceInfo info;
            info.vid = desc.idVendor;
            info.pid = desc.idProduct;
            info.bus = libusb_get_bus_number(device);
            info.addr= libusb_get_device_address(device);
            info.is_candlelight = (desc.idVendor == 0x1d50 && desc.idProduct == 0x606f);

            libusb_device_handle* handle;
            if(libusb_open(device, &handle) == 0){
                unsigned char buffer[256];
                if(desc.iManufacturer){
                    if(libusb_get_string_descriptor_ascii(handle, desc.iManufacturer, buffer, sizeof(buffer)) > 0){
                        info.manufacturer = reinterpret_cast<char*>(buffer);
                    }
                }
                if(desc.iProduct){
                    if(libusb_get_string_descriptor_ascii(handle, desc.iProduct, buffer, sizeof(buffer)) > 0){
                        info.product = reinterpret_cast<char*>(buffer);
                    }
                }
                if(desc.iSerialNumber){
                    if(libusb_get_string_descriptor_ascii(handle, desc.iSerialNumber, buffer, sizeof(buffer)) > 0){
                        info.serial = reinterpret_cast<char*>(buffer);
                    }
                }
                libusb_close(handle);
            }
            devices.push_back(info);
        }
    }

    libusb_free_device_list(devs, 1);
    libusb_exit(scan_ctx);
    return devices;
}

GsUsb* GsUsb::OpenByBusAddr(uint8_t bus, uint8_t address){
    libusb_context* ctx = nullptr;
    int ret = libusb_init(&ctx);
    if(ret < 0) {
        std::cerr << "Failed to initialize libusb for opening device: " << libusb_error_name(ret) << std::endl;
        return nullptr;
    }

    libusb_device** devs;
    ssize_t cnt = libusb_get_device_list(ctx, &devs);
    libusb_device* target_dev = nullptr;

    if(cnt < 0){
        std::cerr << "Failed to get device list: " << libusb_error_name(cnt) << std::endl;
        libusb_exit(ctx);
        return nullptr;
    }

    for(ssize_t i=0; i<cnt; ++i){
        if(libusb_get_bus_number(devs[i]) == bus &&
           libusb_get_device_address(devs[i]) == address){
            target_dev = devs[i];
            break;
        }
    }

    if(!target_dev){
        std::cerr << "Device not found on bus " << static_cast<int>(bus) << " address " << static_cast<int>(address) << std::endl;
        libusb_free_device_list(devs, 1);
        libusb_exit(ctx);
        throw std::runtime_error("Device not found");
    }

    libusb_device_descriptor desc;
    libusb_get_device_descriptor(target_dev, &desc);

    libusb_free_device_list(devs, 1);
    libusb_exit(ctx);

    GsUsb* device = new GsUsb(desc.idVendor, desc.idProduct);
    return device;
}

BitTimingConfig GsUsb::CalculateBitTiming(uint32_t bitrate, uint32_t clock_freq){
    BitTimingConfig config;

    // 40MHz预定义
    if(clock_freq == 40000000){
        switch (bitrate) {
            case 125000:  // 125kbps
                config = {15, 16, 8, 8, 8};
                break;
            case 250000:  // 250kbps
                config = {15, 16, 8, 8, 4};
                break;
            case 500000:  // 500kbps (默认)
                config = {15, 16, 8, 8, 2};
                break;
            case 1000000: // 1Mbps
                config = {15, 16, 8, 8, 1};
                break;
            case 2000000: // 2Mbps (FD 数据段)
                config = {9, 5, 5, 5, 1};
                break;
            case 5000000: // 5Mbps (FD 数据段)
                config = {3, 2, 2, 2, 1};
                break;
            default:
                // 默认 500kbps
                config = {15, 16, 8, 8, 2};
        }
    }
    return config;
}

void GsUsb::SetupCustomBitTiming(const BitTimingConfig& nominal, const BitTimingConfig& data){
    std::cout << "Setting up custom bit timing" << std::endl;

    uint32_t byte_order = 0x0000BEEF;
    SendControl(
        GS_USB_BREQ_HOST_FORMAT, 
        reinterpret_cast<uint8_t*>(&byte_order), 
        0, 
        sizeof(byte_order)
    );   

    uint32_t nominal_bt[5] = {nominal.prop_seg, nominal.phase_seg1, nominal.phase_seg2, nominal.sjw, nominal.brp};
    SendControl(
        GS_USB_BREQ_BITTIMING, 
        reinterpret_cast<uint8_t*>(nominal_bt), 
        0, 
        sizeof(nominal_bt)
    );

    uint32_t data_bt[5] = {data.prop_seg, data.phase_seg1, data.phase_seg2, data.sjw, data.brp};
    SendControl(
        GS_USB_BREQ_DATA_BITTIMING, 
        reinterpret_cast<uint8_t*>(data_bt), 
        0, 
        sizeof(data_bt)
    );

    std::cout << "Custom bit timing setup completed." << std::endl;
}

int GsUsb::GetBusLoad(){
    uint16_t bus_load_raw = 0;

    int ret = libusb_control_transfer(
        dev_handle,
        0xC1, 
        GS_USB_BREQ_GET_BUS_LOAD, 
        0, 
        interface_number, 
        reinterpret_cast<uint8_t*>(&bus_load_raw), 
        sizeof(bus_load_raw), 
        500
    );

    if(ret < 0) {
        std::cerr << "Failed to get bus load." << std::endl;
        return -1; // 返回-1表示获取失败
    }

    return (ret == 2) ? bus_load_raw : -1; // 成功返回总线负载值，否则返回-1
}

DeviceStatus GsUsb::GetDeviceStatus(){
    DeviceStatus device_status;

    int ret = libusb_control_transfer(
        dev_handle, 
        0xC1, 
        GS_USB_BREQ_GET_STATE, 
        0, 
        interface_number, 
        reinterpret_cast<uint8_t*>(&device_status), 
        sizeof(DeviceStatus),
        100
    );

    if(ret != sizeof(DeviceStatus)) {
        std::cerr << "Failed to get device status." << ret << std::endl;
        throw std::runtime_error("Failed to get device status.");
    }
    return device_status;
}