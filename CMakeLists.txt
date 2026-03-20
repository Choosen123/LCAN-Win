cmake_minimum_required(VERSION 3.20)
project(gs_usb)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(LIBUSB REQUIRED libusb-1.0)

add_library(gs_usb_lib gs_usb.cpp)
target_link_libraries(gs_usb_lib PRIVATE ${LIBUSB_LIBRARIES})
target_include_directories(gs_usb_lib PUBLIC ${LIBUSB_INCLUDE_DIRS})

add_executable(test main.cpp)
target_link_libraries(test PRIVATE gs_usb_lib)

set(PYBIND11_FINDPYTHON ON)
find_package(Python 3.13 COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 REQUIRED)

pybind11_add_module(gs_usb binding.cpp)
set_target_properties(gs_usb PROPERTIES PREFIX "" SUFFIX ".pyd")
target_link_libraries(gs_usb PRIVATE gs_usb_lib Python::Module)
target_include_directories(gs_usb PRIVATE C:/msys64/ucrt64/include)


add_custom_command(TARGET gs_usb POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E echo "Copying Python module to project root..."
    COMMAND ${CMAKE_COMMAND} -E copy_if_different 
        $<TARGET_FILE:gs_usb>
        ${CMAKE_SOURCE_DIR}/$<TARGET_FILE_NAME:gs_usb>
    COMMAND ${CMAKE_COMMAND} -E echo "Done: $<TARGET_FILE_NAME:gs_usb>"
    COMMENT "Copying Python module to project root"
)