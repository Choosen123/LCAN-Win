cmake_minimum_required(VERSION 3.20)
project(gs_usb)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

# 2. 设置 libusb 路径
if(WIN32)
    set(LIBUSB_ROOT "${CMAKE_SOURCE_DIR}/libusb")
else()
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(LIBUSB REQUIRED libusb-1.0)
endif()

set(SRC_DIR "${CMAKE_SOURCE_DIR}/src")

# 3. 设置 Python 和 pybind11
find_package(Python COMPONENTS Interpreter Development REQUIRED)
set(PYBIND11_FINDPYTHON ON)
if (NOT pybind11_DIR)
    execute_process(
        COMMAND "${Python_EXECUTABLE}" -c "import pybind11; print(pybind11.get_cmake_dir())"
        OUTPUT_VARIABLE pybind11_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
endif()
message(STATUS "Found pybind11_DIR: ${pybind11_DIR}")
find_package(pybind11 REQUIRED)

# 4. 构建底层的 C++ 逻辑库
add_library(gs_usb_lib STATIC "${SRC_DIR}/gs_usb.cpp")

if(WIN32)
    target_include_directories(gs_usb_lib PUBLIC "${LIBUSB_ROOT}/include")
else()
    target_include_directories(gs_usb_lib PUBLIC ${LIBUSB_INCLUDE_DIRS})
endif()

if(WIN32)
    # 链接 Windows 原生的 libusb 静态库
    target_link_libraries(gs_usb_lib PRIVATE
        "${LIBUSB_ROOT}/VS2022/MS64/static/libusb-1.0.lib")

    # 链接 Windows 系统必要的库
    target_link_libraries(gs_usb_lib PUBLIC
                    SetupAPI.lib
                    Advapi32.lib
                )
else()
    target_link_libraries(gs_usb_lib PRIVATE ${LIBUSB_LIBRARIES})
endif()

# 5. 构建 Python 模块
pybind11_add_module(gs_usb "${SRC_DIR}/binding.cpp")

set_target_properties(gs_usb PROPERTIES PREFIX "")

target_link_libraries(gs_usb PRIVATE gs_usb_lib Python::Module)

# 6. 构建测试程序
add_executable(test "${SRC_DIR}/main.cpp")
target_link_libraries(test PRIVATE gs_usb_lib)

# 7. 自动拷贝
add_custom_command(TARGET gs_usb POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory
        ${CMAKE_SOURCE_DIR}/libs
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        $<TARGET_FILE:gs_usb>
        ${CMAKE_SOURCE_DIR}/libs/$<TARGET_FILE_NAME:gs_usb>
)
