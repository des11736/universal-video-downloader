#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UVD WebUI 图标生成脚本(v2 精致版)

设计:
- 圆角方形背景 + 蓝色到青色的垂直渐变
- 边缘高光(内描边)增强立体感
- 白色下载箭头(更粗的箭杆 + 饱满的箭头三角)
- 中央叠加品牌蓝填充的视频播放三角形(镂空效果)
- 底部白色托盘横线(带圆角)

输出: assets/icons/uvd.ico(多尺寸 16/32/48/64/128/256)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# 品牌色
BRAND_BLUE = (24, 144, 255, 255)      # #1890ff
BRAND_CYAN = (0, 200, 220, 255)       # #00c8dc 渐变终点
BRAND_BLUE_DARK = (8, 96, 180, 255)   # 描边深蓝
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)

# 画布尺寸
SIZE = 256
CENTER = SIZE // 2


def _vertical_gradient(size: int, top_color, bottom_color) -> Image.Image:
    """生成垂直渐变图(用于圆角方形背景填充)。"""
    grad = Image.new("RGBA", (size, size), TRANSPARENT)
    pixels = grad.load()
    for y in range(size):
        # 线性插值
        ratio = y / max(size - 1, 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        a = int(top_color[3] + (bottom_color[3] - top_color[3]) * ratio)
        for x in range(size):
            pixels[x, y] = (r, g, b, a)
    return grad


def draw_icon() -> Image.Image:
    """绘制 256x256 精致图标并返回 RGBA 图像。"""
    img = Image.new("RGBA", (SIZE, SIZE), TRANSPARENT)

    # 1. 圆角方形渐变背景(圆角半径 56,留 12px 外边距)
    radius = 56
    margin = 12
    bg_box = (margin, margin, SIZE - margin, SIZE - margin)

    # 先画渐变到临时图层,再用圆角方形 mask 贴合
    gradient = _vertical_gradient(SIZE, BRAND_BLUE, BRAND_CYAN)
    mask = Image.new("L", (SIZE, SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(bg_box, radius=radius, fill=255)
    img.paste(gradient, (0, 0), mask)

    # 2. 边缘内高光(白色半透明内描边,营造立体感)
    draw = ImageDraw.Draw(img)
    highlight_box = (margin + 2, margin + 2, SIZE - margin - 2, SIZE - margin - 2)
    draw.rounded_rectangle(
        highlight_box,
        radius=radius - 2,
        outline=(255, 255, 255, 90),
        width=2,
    )

    # 3. 顶部高光带(模拟光源从上方照射)
    glow = Image.new("RGBA", (SIZE, SIZE), TRANSPARENT)
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.rounded_rectangle(
        (margin + 6, margin + 6, SIZE - margin - 6, margin + 50),
        radius=radius - 8,
        fill=(255, 255, 255, 50),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=8))
    img = Image.alpha_composite(img, glow)

    draw = ImageDraw.Draw(img)

    # 4. 白色下载箭头(更粗、更饱满)
    #    竖向箭杆
    shaft_half_width = 18
    shaft_left = CENTER - shaft_half_width
    shaft_right = CENTER + shaft_half_width
    shaft_top = 56
    shaft_bottom = 132
    draw.rounded_rectangle(
        (shaft_left, shaft_top, shaft_right, shaft_bottom),
        radius=8,
        fill=WHITE,
    )

    #    箭头三角形(指向下方,饱满倒三角)
    arrow_top_y = 116
    arrow_point_y = 180
    arrow_half_width = 52
    arrow_left = CENTER - arrow_half_width
    arrow_right = CENTER + arrow_half_width
    draw.polygon(
        [
            (arrow_left, arrow_top_y),
            (arrow_right, arrow_top_y),
            (CENTER, arrow_point_y),
        ],
        fill=WHITE,
    )

    # 5. 中央叠加视频播放三角形(品牌蓝填充,镂空效果)
    #    等腰三角形指向右,稍偏右让视觉平衡
    play_size = 26
    play_left = CENTER - play_size // 2 + 2
    play_right = play_left + play_size
    play_top_y = 86
    play_bottom_y = 118
    draw.polygon(
        [
            (play_left, play_top_y),
            (play_left, play_bottom_y),
            (play_right, (play_top_y + play_bottom_y) // 2),
        ],
        fill=BRAND_BLUE_DARK,
    )

    # 6. 底部白色托盘横线(圆角矩形)
    tray_left = CENTER - 62
    tray_right = CENTER + 62
    tray_top = 196
    tray_bottom = 214
    draw.rounded_rectangle(
        (tray_left, tray_top, tray_right, tray_bottom),
        radius=9,
        fill=WHITE,
    )

    return img


def main() -> None:
    """生成图标文件。"""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    icons_dir = project_root / "assets" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    output_path = icons_dir / "uvd.ico"
    png_preview_path = icons_dir / "uvd_preview.png"

    img = draw_icon()

    # 多尺寸 ICO 输出
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(output_path, format="ICO", sizes=sizes)

    # 同时导出 PNG 预览(放大到 512x512 方便查看)
    preview = img.resize((512, 512), Image.LANCZOS)
    preview.save(png_preview_path, format="PNG")

    print(f"图标已生成: {output_path}")
    print(f"包含尺寸: {sizes}")
    print(f"预览图: {png_preview_path}")


if __name__ == "__main__":
    main()
