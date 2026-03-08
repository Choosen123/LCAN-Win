#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include "gs_usb.hpp"

namespace py = pybind11;

// Python 友好的帧数据结构
struct PyCANFrame {
    uint32_t can_id;
    uint8_t dlc;
    uint8_t flags;
    py::bytes data;
    double timestamp;
    bool is_fd;
    bool is_brs;
    
    PyCANFrame(const CANFrame& frame) 
        : can_id(frame.can_id)
        , dlc(frame.dlc)
        , flags(frame.flags)
        , data(reinterpret_cast<const char*>(frame.data.data()), frame.data.size())
        , timestamp(frame.timestamp)
        , is_fd(frame.is_fd())
        , is_brs(frame.is_brs())
    {}
    
    py::dict to_dict() const {
        py::dict d;
        d["can_id"] = can_id;
        d["dlc"] = dlc;
        d["flags"] = flags;
        d["data"] = data;
        d["timestamp"] = timestamp;
        d["is_fd"] = is_fd;
        d["is_brs"] = is_brs;
        return d;
    }
};

// Python 包装类
class PyGsUsb {
private:
    std::unique_ptr<GsUsb> device_;
    
public:
    PyGsUsb(uint16_t vendor_id, uint16_t product_id) {
        // 释放 GIL，允许其他 Python 线程运行
        py::gil_scoped_release release;
        device_ = std::make_unique<GsUsb>(vendor_id, product_id);
    }
    
    void setup(uint32_t nominal_bitrate = 500000, uint32_t data_bitrate = 2000000) {
        py::gil_scoped_release release;
        device_->Setup(nominal_bitrate, data_bitrate);
    }

    void setup_custom(const BitTimingConfig& nominal, const BitTimingConfig& data) {
        py::gil_scoped_release release;
        device_->SetupCustomBitTiming(nominal, data);
    }
    
    void start(bool use_fd = true) {
        py::gil_scoped_release release;
        device_->Start(use_fd);
    }
    
    void stop() {
        py::gil_scoped_release release;
        device_->Stop();
    }
    
    bool send_frame(uint32_t can_id, const py::bytes& data, bool use_fd = true, bool use_brs = true) {
        std::string data_str = data;
        std::vector<uint8_t> data_vec(data_str.begin(), data_str.end());
        
        py::gil_scoped_release release;
        // 调用修改后的底层函数
        return device_->SendFrame(can_id, data_vec, use_fd, use_brs);
    }
    
    py::list get_received_frames(size_t max_count = 100) {
        py::list result;
        
        std::vector<CANFrame> frames;
        {
            py::gil_scoped_release release;
            frames = device_->GetReceivedFrames(max_count);
        }
        
        // 转换为 Python 字典列表
        for (const auto& frame : frames) {
            PyCANFrame py_frame(frame);
            result.append(py_frame.to_dict());
        }
        
        return result;
    }

    
    uint64_t get_rx_count() const {
        return device_->GetRxCount();
    }
    
    uint64_t get_tx_count() const {
        return device_->GetTxCount();
    }
    
    bool is_rx_thread_running() const {
        return device_->IsRxThreadRunning();
    }
};

// 模块定义
PYBIND11_MODULE(gs_usb, m) {
    m.doc() = "GS_USB CAN FD interface module";

    py::class_<USBDeviceInfo>(m, "USBDeviceInfo")
        .def_readonly("vid", &USBDeviceInfo::vid)
        .def_readonly("pid", &USBDeviceInfo::pid)
        .def_readonly("bus", &USBDeviceInfo::bus)
        .def_readonly("addr", &USBDeviceInfo::addr)
        .def_readonly("manufacturer", &USBDeviceInfo::manufacturer)
        .def_readonly("product", &USBDeviceInfo::product)
        .def_readonly("serial", &USBDeviceInfo::serial)
        .def_readonly("is_candlelight", &USBDeviceInfo::is_candlelight)
        .def("__str__", &USBDeviceInfo::to_string)
        .def("__repr__", &USBDeviceInfo::to_string);
    
    py::class_<BitTimingConfig>(m, "BitTimingConfig")
        .def(py::init<>())
        .def_readwrite("prop_seg", &BitTimingConfig::prop_seg)
        .def_readwrite("phase_seg1", &BitTimingConfig::phase_seg1)
        .def_readwrite("phase_seg2", &BitTimingConfig::phase_seg2)
        .def_readwrite("sjw", &BitTimingConfig::sjw)
        .def_readwrite("brp", &BitTimingConfig::brp);
    
    py::class_<PyGsUsb>(m, "GsUsbFDCAN")
        .def(py::init<uint16_t, uint16_t>(),
             py::arg("vid") = 0x1d50,
             py::arg("pid") = 0x606f,
             "Initialize GS_USB device\n\n"
             "Parameters:\n"
             "  vid: Vendor ID (default: 0x1d50)\n"
             "  pid: Product ID (default: 0x606f)")
        
        .def("setup", &PyGsUsb::setup,
             py::arg("nominal_bitrate") = 500000,
             py::arg("data_bitrate") = 2000000,
             "Configure CAN bitrates\n\n"
             "Parameters:\n"
             "  nominal_bitrate: Arbitration phase bitrate in bps (default: 500000)\n"
             "  data_bitrate: Data phase bitrate in bps (default: 2000000)")

        .def("setup_custom", &PyGsUsb::setup_custom,
             py::arg("nominal"),
             py::arg("data"),
             "Configure with custom bit timing")
            
        .def("start", &PyGsUsb::start,
             py::arg("use_fd") = true,
             "Start CAN communication\n\n"
             "Parameters:\n"
             "  use_fd: Enable CAN FD mode (default: True)")
        
        .def("stop", &PyGsUsb::stop,
             "Stop CAN communication")
        
        .def("send_frame", &PyGsUsb::send_frame, 
            py::arg("can_id"), py::arg("data"), py::arg("use_fd")=true, py::arg("use_brs")=true)
        
        .def("get_received_frames", &PyGsUsb::get_received_frames,
             py::arg("max_count") = 100,
             "Get received CAN frames\n\n"
             "Parameters:\n"
             "  max_count: Maximum number of frames to retrieve (default: 100)\n\n"
             "Returns:\n"
             "  list[dict]: List of received frames, each frame is a dict with keys:\n"
             "    - can_id: CAN identifier\n"
             "    - dlc: Data length code\n"
             "    - flags: Frame flags\n"
             "    - data: Frame data as bytes\n"
             "    - timestamp: Reception timestamp\n"
             "    - is_fd: True if CAN FD frame\n"
             "    - is_brs: True if bit rate switching was used")
        
        .def("get_rx_count", &PyGsUsb::get_rx_count,
             "Get total received frame count")
        
        .def("get_tx_count", &PyGsUsb::get_tx_count,
             "Get total transmitted frame count")
        
        .def("is_rx_thread_running", &PyGsUsb::is_rx_thread_running,
             "Check if receive thread is running")
        
        .def("__repr__", [](const PyGsUsb& self) {
            return "<GsUsbFDCAN RX=" + std::to_string(self.get_rx_count()) +
                   " TX=" + std::to_string(self.get_tx_count()) + ">";
        });
    
    m.def("scan_devices", []() {
        py::gil_scoped_release release;
        return GsUsb::ScanDevices();
    }, "Scan all USB devices");
    
    m.def("calculate_bit_timing", &GsUsb::CalculateBitTiming,
          py::arg("bitrate"),
          py::arg("clock_freq") = 40000000,
          "Calculate bit timing configuration for given bitrate");

    // 版本信息
    m.attr("__version__") = "1.0.0";
}