from PIL import Image

def ico_to_png(ico_path, png_path):
    # 打开 ico 文件
    img = Image.open(ico_path)
    
    # ico 可能包含多个尺寸，img.info['sizes'] 可以查看
    # 寻找最大的尺寸
    icon_sizes = img.info.get('sizes', [])
    print(f"该图标包含尺寸: {icon_sizes}")

    # 如果有多张，我们取最后一张（通常是最高清的）
    # 或者直接让 Pillow 自动选择最佳质量
    img.save(png_path, format="PNG")
    print(f"转换成功！高清 PNG 已保存至: {png_path}")

def convert_to_transparent_ico(png_path, ico_path):
    img = Image.open(png_path)
    
    # 强制进入 RGBA 模式
    img = img.convert("RGBA")
    
    # 包含所有 Windows 需要的尺寸
    sizes = [(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)]
    
    # 保存时，Pillow 会自动保留 Alpha 通道
    img.save(ico_path, format='ICO', sizes=sizes)
    print("透明 ICO 转换完成！")


def create_ultra_clear_ico(png_path, ico_path):
    # 1. 打开原始超大图片（建议原始图片是 1024x1024 或 512x512）
    master_img = Image.open(png_path).convert("RGBA")
    
    # 2. 定义 Windows 需要的所有标准尺寸
    # 包含 256px 是为了让桌面大图标清晰
    # 包含 16/32/48 是为了让任务栏和列表清晰
    target_sizes = [16, 32, 48, 64, 128, 256]
    
    icon_layers = []
    for size in target_sizes:
        # 使用 Resampling.LANCZOS 进行高质量缩放
        # 这是保持边缘锐利的关键
        resized_img = master_img.resize((size, size), Image.Resampling.LANCZOS)
        icon_layers.append(resized_img)
    
    # 3. 保存。设置 bitmap_format='png' (对于256px尺寸) 
    # 现代 Windows 图标在 256 尺寸下内部其实是一个 PNG，这样支持完美透明和超清
    icon_layers[0].save(
        ico_path, 
        format='ICO', 
        append_images=icon_layers[1:],
        sizes=[(s, s) for s in target_sizes]
    )
    print("超清透明 ICO 已生成！")

def remove_white_background(input_path, output_path):
    img = Image.open(input_path).convert("RGBA")
    datas = img.getdata()

    new_data = []
    for item in datas:
        # 如果像素点接近纯白色 (255, 255, 255)，则将其 Alpha 通道设为 0 (透明)
        # 容差设为 240 可以处理不是纯白的浅灰色边缘
        if item[0] > 50 and item[1] > 240 and item[2] > 240:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)

    img.putdata(new_data)
    img.save(output_path, "PNG")
    print(f"透明背景 PNG 已生成: {output_path}")

def remove_white_background_modern(input_path, output_path, threshold=220):
    """
    input_path: 输入图片路径
    output_path: 输出路径
    threshold: 亮度阈值 (0-255)。越低抠得越狠。建议 200-230。
    """
    # 1. 打开图片并确保是 RGBA 模式
    img = Image.open(input_path).convert("RGBA")
    
    # 2. 获取亮度通道 (L)
    # 相比于手动 getdata()，这种方法速度极快且无警告
    l_channel = img.convert("L")
    
    # 3. 创建 Alpha 蒙版 (核心逻辑)
    # 逻辑：亮度高于 250 的像素设为完全透明 (0)
    #       亮度低于 threshold 的像素设为完全不透明 (255)
    #       中间部分进行线性过渡，从而消除白边/锯齿
    def map_alpha(x):
        if x > 250:
            return 0
        if x < threshold:
            return 255
        # 线性插值计算透明度 (实现平滑边缘)
        return int(255 * (255 - x) / (255 - threshold))

    new_alpha = l_channel.point(map_alpha)
    
    # 4. 将新生成的 Alpha 通道应用到原图
    img.putalpha(new_alpha)
    
    # 5. 保存
    img.save(output_path, "PNG")
    print(f"✅ 透明背景 PNG 已生成 (无警告版本): {output_path}")

# 调用执行
# remove_white_background_modern("old_logo.png", "logo_transparent.png", threshold=210)
# remove_white_background_modern("LCAN-View.png", "LCAN-View_transparent.png", threshold=130)
# ico_to_png("pcan.ico", "pcan.png")
# create_ultra_clear_ico("LCAN-View_transparent.png", "LCAN-View.ico")
convert_to_transparent_ico("LCAN-View_.png", "LCAN-View.ico")