#pragma once
#include <libusb.h>
#include <vector>
#include <atomic>
#include <thread>
#include <queue>
#include <mutex>
#include <string>
#include <sstream>

// CAN错误帧定义
#define CAN_ERR_FLAG							0x20000000U /* error message frame */

#define CAN_ERR_DLC								8 /* dlc for error message frames */

enum gs_usb_request_type {
	GS_USB_BREQ_HOST_FORMAT = 0,
	GS_USB_BREQ_BITTIMING,
	GS_USB_BREQ_MODE,
	GS_USB_BREQ_BERR,
	GS_USB_BREQ_BT_CONST,
	GS_USB_BREQ_DEVICE_CONFIG,
	GS_USB_BREQ_TIMESTAMP,
	GS_USB_BREQ_IDENTIFY,
	GS_USB_BREQ_GET_USER_ID,    //not implemented
	GS_USB_BREQ_SET_USER_ID,    //not implemented
	GS_USB_BREQ_DATA_BITTIMING,
	GS_USB_BREQ_BT_CONST_EXT,
	GS_USB_BREQ_SET_TERMINATION,
	GS_USB_BREQ_GET_TERMINATION,
	GS_USB_BREQ_GET_STATE,
	GS_USB_BREQ_GET_BUS_LOAD,
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
    bool is_error = false;
    bool is_fd() const { return flags & GS_CAN_FLAG_FD; }
    bool is_brs() const { return flags & GS_CAN_FLAG_BRS; }
};

struct USBDeviceInfo{
    uint16_t vid;
    uint16_t pid;
    uint8_t bus;
    uint8_t addr;
    std::string manufacturer;
    std::string product;
    std::string serial;
    bool is_candlelight;

    std::string to_string() const {
        char buf[256];
        snprintf(buf, sizeof(buf), "VID:0x%04X PID:0x%04X Bus:%d Addr:%d - %s %s (SN:%s)",
                vid, pid, bus, addr, 
                manufacturer.c_str(), product.c_str(), serial.c_str());
        return std::string(buf);
    }
};

struct BitTimingConfig{
    uint32_t prop_seg;
    uint32_t phase_seg1;
    uint32_t phase_seg2;
    uint32_t sjw;
    uint32_t brp;
};

struct DeviceStatus {
    uint32_t node_state;
    uint32_t rec;
    uint32_t tec;
};


class GsUsb{
public:
    GsUsb(uint16_t vendor_id, uint16_t product_id);
    ~GsUsb();

    void Setup(uint32_t nominal_bitrate = 1000000, uint32_t data_bitrate = 2000000);
    void Start(bool use_fd = false);
    void Stop();

    bool SendFrame(uint32_t can_id, const std::vector<uint8_t>& data, bool use_fd = false, bool use_brs = false);
    std::vector<CANFrame> GetReceivedFrames(size_t max_count = 100);

    uint64_t GetRxCount() const { return rx_count.load(); };
    uint64_t GetTxCount() const { return tx_count.load(); };
    bool IsRxThreadRunning() const { return rx_thread_running.load(); }

    static std::vector<USBDeviceInfo> ScanDevices();
    static GsUsb* OpenByBusAddr(uint8_t bus, uint8_t address);
    static BitTimingConfig CalculateBitTiming(uint32_t bitrate, uint32_t clock_freq = 40000000);
    void SetupCustomBitTiming(const BitTimingConfig& nominal, const BitTimingConfig& data);
    int GetBusLoad();
    DeviceStatus GetDeviceStatus();

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
    static uint8_t DlcCodeToLen(uint8_t dlc_code);
    static double GetTimestamp();
};
