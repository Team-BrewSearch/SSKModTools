import struct
from PIL import Image
import tkinter as tk
from tkinter import filedialog, messagebox


def parse_5tx(data):
    """Parse 5TX file using IMGE header for dimensions and encoding"""
    if data[0:4] != b'NTTX':
        raise ValueError("Invalid 5TX file")

    # Find headers
    palette_start = data.find(b'PALT')
    imge_start = data.find(b'IMGE')
    if palette_start == -1 or imge_start == -1:
        raise ValueError("Missing PALT or IMGE header")

    # Parse palette
    palette_colors = struct.unpack_from('<I', data, palette_start + 8)[0]
    palette_data = data[palette_start + 12:palette_start + 12 + palette_colors * 2]
    palette_rgb = [(
        (color & 0x1F) * 255 // 31,
        ((color >> 5) & 0x1F) * 255 // 31,
        ((color >> 10) & 0x1F) * 255 // 31
    ) for color in struct.unpack_from(f'<{palette_colors}H', palette_data)]

    # Parse image header and data
    width, height = struct.unpack_from('<HH', data, imge_start + 12)
    encoding = 'I8' if data[imge_start + 8] == 0x04 else 'I4'

    image_data = data[imge_start + 20:imge_start + 20 + (width * height // (1 if encoding == 'I8' else 2))]

    return palette_rgb, image_data, width, height, encoding


def decode_image_data(image_data, width, height, encoding):
    """Decode image data based on encoding type"""
    if encoding == 'I8':
        pixels = list(image_data[:width * height])
    else:  # I4
        pixels = []
        for byte in image_data[:(width * height) // 2]:
            pixels.extend([byte & 0x0F, (byte >> 4) & 0x0F])

    pixels.extend([0] * (width * height - len(pixels)))
    return pixels[:width * height]


def convert_5tx_to_png(tx_data, output_path):
    """Convert 5TX file to PNG format with transparency"""
    try:
        palette, image_data, width, height, encoding = parse_5tx(tx_data)
        pixels = decode_image_data(image_data, width, height, encoding)

        # Detailed print information
        print("=== 5TX File Analysis ===")
        print(f"Dimensions: {width} x {height} pixels")
        print(f"Encoding: {encoding}")
        print(f"Palette Colors: {len(palette)}")
        print(f"Image Data Size: {len(image_data)} bytes")
        print(f"Total Pixels: {width * height}")

        # Analyze pixel usage
        unique_pixels = len(set(pixels))
        print(f"Unique Color Indices Used: {unique_pixels}")

        # Check for magenta (#FF00FF) in palette and replace with transparent
        transparent_index = None
        for i, color in enumerate(palette):
            if color == (255, 0, 255):  # Magenta
                transparent_index = i
                print(f"Transparency: Found magenta at palette index {i}")
                break

        if transparent_index is not None:
            transparent_pixels = pixels.count(transparent_index)
            print(f"Transparent Pixels: {transparent_pixels} ({transparent_pixels * 100 // (width * height)}%)")
        else:
            print("Transparency: No magenta color found in palette")

        print("Palette Colors:")
        for i, color in enumerate(palette):
            status = " (TRANSPARENT)" if color == (255, 0, 255) else ""
            print(f"  [{i:3d}] RGB({color[0]:3d}, {color[1]:3d}, {color[2]:3d}){status}")

        print("========================")

        # Create RGBA image for transparency support
        img = Image.new('RGBA', (width, height))
        rgba_pixels = []

        for pixel in pixels:
            if pixel == transparent_index:
                rgba_pixels.append((0, 0, 0, 0))  # Fully transparent
            else:
                r, g, b = palette[pixel]
                rgba_pixels.append((r, g, b, 255))  # Fully opaque

        img.putdata(rgba_pixels)
        img.save(output_path, 'PNG')
        return True

    except Exception as e:
        print(f"Error during conversion: {e}")
        return False


def convert_5tx_file(input_path, output_path):
    """Convert 5TX file to PNG"""
    try:
        print(f"Converting: {input_path} -> {output_path}")
        with open(input_path, 'rb') as f:
            data = f.read()
            print(f"File Size: {len(data)} bytes")
            return convert_5tx_to_png(data, output_path)
    except Exception as e:
        print(f"Error reading file: {e}")
        return False


def main():
    root = tk.Tk()
    root.withdraw()

    input_file = filedialog.askopenfilename(
        title="Select 5TX file",
        filetypes=[("5TX files", "*.5tx"), ("All files", "*.*")]
    )
    if not input_file:
        return

    output_file = filedialog.asksaveasfilename(
        title="Save PNG as",
        defaultextension=".png",
        filetypes=[("PNG files", "*.png")]
    )
    if not output_file:
        return

    if convert_5tx_file(input_file, output_file):
        print("✅ Conversion completed successfully!")
        messagebox.showinfo("Success", "File converted successfully")
    else:
        print("❌ Conversion failed!")
        messagebox.showerror("Error", "Conversion failed")


if __name__ == "__main__":
    main()