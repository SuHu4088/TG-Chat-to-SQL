#!/usr/bin/env python3
"""生成 App 图标（纯代码绘制，无外部素材）。

输出 `build/AppIcon.icns`，供 PyInstaller 使用。
"""

import os
import subprocess
import sys

import objc
from AppKit import (
    NSBezierPath,
    NSBitmapImageRep,
    NSCalibratedRGBColorSpace,
    NSColor,
    NSGradient,
    NSGraphicsContext,
    NSImage,
    NSMakeRect,
    NSMutableParagraphStyle,
    NSFont,
    NSFontAttributeName,
    NSFontWeightSemibold,
    NSForegroundColorAttributeName,
    NSParagraphStyleAttributeName,
    NSTextAlignmentCenter,
)
from Foundation import NSData, NSDictionary, NSString

sizes = [16, 32, 64, 128, 256, 512, 1024]
out_dir = os.path.join("build", "icon.iconset")
os.makedirs(out_dir, exist_ok=True)


def draw(size):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bitmapFormat_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0, 0
    )
    rep.setSize_((size, size))

    NSGraphicsContext.saveGraphicsState()
    context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.setCurrentContext_(context)

    rect = NSMakeRect(size * 0.06, size * 0.06, size * 0.88, size * 0.88)
    radius = size * 0.22
    path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)

    gradient = NSGradient.alloc().initWithColors_([
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.17, 0.36, 0.86, 1.0),
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.36, 0.16, 0.72, 1.0),
    ])
    gradient.drawInBezierPath_angle_(path, -60)

    # 高光
    highlight = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(size * 0.06, size * 0.52, size * 0.88, size * 0.42),
        radius * 0.6, radius * 0.6,
    )
    NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.08).setFill()
    highlight.fill()

    text = "TG"
    font_size = size * 0.42
    font = NSFont.boldSystemFontOfSize_(font_size)
    paragraph = NSMutableParagraphStyle.alloc().init()
    paragraph.setAlignment_(NSTextAlignmentCenter)
    attrs = {
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: NSColor.whiteColor(),
        NSParagraphStyleAttributeName: paragraph,
    }
    text_rect = NSMakeRect(0, size * 0.26, size, font_size * 1.2)
    NSString.stringWithString_(text).drawInRect_withAttributes_(text_rect, attrs)

    NSGraphicsContext.restoreGraphicsState()

    return rep.representationUsingType_properties_(4, {})  # NSBitmapImageFileTypePNG


ICONSET = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

for name, px in ICONSET:
    png = draw(px)
    path = os.path.join(out_dir, name)
    png.writeToFile_atomically_(path, True)
    print("wrote", path)

subprocess.run(["iconutil", "-c", "icns", out_dir, "-o", "build/AppIcon.icns"], check=True)
print("生成 build/AppIcon.icns")
