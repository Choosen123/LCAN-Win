#pragma once
#include <libusb.h>
#include <vector>
#include <atomic>
#include <thread>
#include <queue>
#include <mutex>

enum gs_usb_request_type {
    GS_USB_BREQ_HOST_FORMAT = 0,
    GS_USB_BREQ_BITTIMING = 1,
    GS_USB_BREQ_MODE = 2,
    GS_USB_BREQ_DATA_BITTIMING = 10,
    GS_USB_BREQ_BERR = 9
};

enum gs_usb_mode_constants {
    GS_CAN_MODE_START = 1,
    GS_CAN_MODE_RESET = 0,
    GS_CAN_MODE_FD = 0x0100
};

enum gs_usb_frame_flags {
    GS_CAN_FLAG_FD = 0x02,
    GS_CAN_FLAG_BRS = 0x04
};

struct CANFrame{
    uint32_t can_id;
    uint8_t dlc;
    uint8_t flags;
    std::vector<uint8_t> data;
    double timestamp;
    bool is_fd() const { return flags & GS_CAN_FLAG_FD; }
    bool is_brs() const { return flags & GS_CAN_FLAG_BRS; }
};

class GsUsb{
public:
    GsUsb(uint16_t vendor_id, uint16_t product_id);
    ~GsUsb();

    void Setup(uint32_t nominal_bitrate = 1000000, uint32_t data_bitrate = 2000000);
    void Start(bool use_fd = false);
    void Stop();

    bool SendFDFrame(uint32_t can_id, const std::vector<uint8_t>& data, bool use_brs = false);
    std::vector<CANFrame> GetReceivedFrames(size_t max_count = 100);

    uint64_t GetRxCount() const { return rx_count.load(); };
    uint64_t GetTxCount() const { return tx_count.load(); };
    bool IsRxThreadRunning() const { return rx_thread_running.load(); }

private:
    libusb_context* ctx = nullptr;
    libusb_device* dev;
    libusb_device_handle* dev_handle = nullptr;
    int interface_number = 0;

    std::thread rx_thread;
    std::atomic<bool> rx_thread_running{false};
    std::atomic<bool> stop_flag{false};

    std::queue<CANFrame> rx_queue;
    std::mutex rx_queue_mutex;
    static constexpr size_t MAX_QUEUE_SIZE = 100000;


    std::atomic<uint64_t> rx_count{0};
    std::atomic<uint64_t> tx_count{0};

    int SendControl(uint8_t request, const uint8_t* data, uint16_t value, uint16_t length);
    void ReceiveLoop();
    void DrainRxBuffer();

    static uint8_t LenToDlcCode(uint16_t len);
    static double GetTimestamp();
};
