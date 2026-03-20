cmake_minimum_required(VERSION 3.20)
project(gs_usb)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# 1. 彻底删除 PkgConfig，因为它在 Windows 上经常会乱指 MSYS2 的路径
# find_package(PkgConfig REQUIRED)  <-- 删除这行

# 2. 设置 libusb 路径 (假设你已经下载了官方 Windows 库并放在了项目下的 libusb 目录)
set(LIBUSB_ROOT "${CMAKE_SOURCE_DIR}/libusb")

# 3. 设置 Python 和 pybind11
set(PYBIND11_FINDPYTHON ON)
find_package(Python 3.13 COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 REQUIRED)

# 4. 构建底层的 C++ 逻辑库
add_library(gs_usb_lib STATIC gs_usb.cpp)

# 关键：只使用你手动下载的 libusb 头文件，绝不引用 MSYS2
target_include_directories(gs_usb_lib PUBLIC "${LIBUSB_ROOT}/include")

# 链接 Windows 原生的 libusb 静态库
# 这样打包出的 pyd 就不再依赖 libusb-1.0.dll，更加稳健
target_link_libraries(gs_usb_lib PRIVATE "${LIBUSB_ROOT}/VS2022/MS64/static/libusb-1.0.lib")

# 链接 Windows 系统必要的库 (libusb 静态链接时必须包含这些)
target_link_libraries(gs_usb_lib PUBLIC SetupAPI.lib Advapi32.lib)
# 5. 构建 Python 模块
pybind11_add_module(gs_usb binding.cpp)

# 关键：彻底删除 C:/msys64/ucrt64/include ！！！
# target_include_directories(gs_usb PRIVATE C:/msys64/ucrt64/include) <-- 删除这行

set_target_properties(gs_usb PROPERTIES PREFIX "" SUFFIX ".pyd")
target_link_libraries(gs_usb PRIVATE gs_usb_lib Python::Module)

# 6. 构建测试程序 (可选)
add_executable(test main.cpp)
target_link_libraries(test PRIVATE gs_usb_lib)

# 7. 自动拷贝
add_custom_command(TARGET gs_usb POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Copying Python module to project root..."
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        $<TARGET_FILE:gs_usb>
        ${CMAKE_SOURCE_DIR}/$<TARGET_FILE_NAME:gs_usb>
    COMMAND ${CMAKE_COMMAND} -E echo "Done: $<TARGET_FILE_NAME:gs_usb>"
)
