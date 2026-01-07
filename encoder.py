import struct
from PIL import Image
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os


class FiveTXEncoder:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("5TX Encoder")
        self.root.geometry("500x400")

        self.setup_ui()

    def setup_ui(self):
        # Input file selection
        tk.Label(self.root, text="Input Image (PNG/BMP):").pack(pady=5)
        self.input_frame = tk.Frame(self.root)
        self.input_frame.pack(pady=5, fill='x', padx=20)

        self.input_var = tk.StringVar()
        tk.Entry(self.input_frame, textvariable=self.input_var, width=40).pack(side='left', fill='x', expand=True)
        tk.Button(self.input_frame, text="Browse", command=self.browse_input).pack(side='right', padx=5)

        # Output file selection
        tk.Label(self.root, text="Output 5TX File:").pack(pady=5)
        self.output_frame = tk.Frame(self.root)
        self.output_frame.pack(pady=5, fill='x', padx=20)

        self.output_var = tk.StringVar()
        tk.Entry(self.output_frame, textvariable=self.output_var, width=40).pack(side='left', fill='x', expand=True)
        tk.Button(self.output_frame, text="Browse", command=self.browse_output).pack(side='right', padx=5)

        # Encoding options
        options_frame = tk.LabelFrame(self.root, text="Encoding Options", padx=10, pady=10)
        options_frame.pack(pady=10, fill='x', padx=20)

        # Encoding type
        tk.Label(options_frame, text="Encoding:").grid(row=0, column=0, sticky='w')
        self.encoding_var = tk.StringVar(value="I8")
        encoding_combo = ttk.Combobox(options_frame, textvariable=self.encoding_var, values=["I8", "I4"],
                                      state="readonly")
        encoding_combo.grid(row=0, column=1, sticky='w', padx=5)

        # Max colors
        tk.Label(options_frame, text="Max Colors:").grid(row=1, column=0, sticky='w')
        self.colors_var = tk.StringVar(value="256")
        colors_combo = ttk.Combobox(options_frame, textvariable=self.colors_var, values=["16", "256"], state="readonly")
        colors_combo.grid(row=1, column=1, sticky='w', padx=5)

        # Dithering
        tk.Label(options_frame, text="Dithering:").grid(row=2, column=0, sticky='w')
        self.dither_var = tk.StringVar(value="NONE")
        dither_combo = ttk.Combobox(options_frame, textvariable=self.dither_var,
                                    values=["NONE", "FLOYDSTEINBERG", "ORDERED"], state="readonly")
        dither_combo.grid(row=2, column=1, sticky='w', padx=5)

        # Update colors based on encoding
        encoding_combo.bind('<<ComboboxSelected>>', self.update_color_limit)

        # Convert button
        tk.Button(self.root, text="Convert to 5TX", command=self.convert,
                  bg='#4CAF50', fg='white', font=('Arial', 12)).pack(pady=20)

        # Status
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(self.root, textvariable=self.status_var).pack()

    def update_color_limit(self, event=None):
        if self.encoding_var.get() == "I4":
            self.colors_var.set("16")
        else:
            self.colors_var.set("256")

    def browse_input(self):
        filename = filedialog.askopenfilename(
            title="Select input image",
            filetypes=[("Image files", "*.png *.bmp"), ("PNG files", "*.png"), ("BMP files", "*.bmp"),
                       ("All files", "*.*")]
        )
        if filename:
            self.input_var.set(filename)
            # Auto-set output filename
            base = os.path.splitext(filename)[0]
            self.output_var.set(base + ".5tx")

    def browse_output(self):
        filename = filedialog.asksaveasfilename(
            title="Save 5TX as",
            defaultextension=".5tx",
            filetypes=[("5TX files", "*.5tx")]
        )
        if filename:
            self.output_var.set(filename)

    def convert_image_to_indexed(self, img, max_colors, dither):
        """Convert image to indexed color mode with optimized palette"""
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Find transparent pixels
        transparency_mask = []
        pixels = list(img.getdata())
        for pixel in pixels:
            transparency_mask.append(pixel[3] < 128)  # Alpha < 128 = transparent

        # Convert to RGB for quantization (without alpha)
        rgb_img = img.convert('RGB')

        # Quantize to limited colors
        if dither == "NONE":
            dithered_img = rgb_img.quantize(colors=max_colors, method=Image.MEDIANCUT, dither=Image.NONE)
        elif dither == "FLOYDSTEINBERG":
            dithered_img = rgb_img.quantize(colors=max_colors, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
        else:  # ORDERED
            dithered_img = rgb_img.quantize(colors=max_colors, method=Image.MEDIANCUT, dither=Image.ORDERED)

        # Get palette and convert to RGB tuples
        palette = dithered_img.getpalette()
        rgb_palette = []
        for i in range(0, len(palette), 3):
            rgb_palette.append((palette[i], palette[i + 1], palette[i + 2]))

        # Replace transparent color with magenta
        magenta_index = None
        for i, color in enumerate(rgb_palette):
            if color == (255, 0, 255):
                magenta_index = i
                break

        if magenta_index is None:
            # Add magenta to palette if not present
            if len(rgb_palette) < max_colors:
                rgb_palette.append((255, 0, 255))
                magenta_index = len(rgb_palette) - 1
            else:
                # Replace last color with magenta
                rgb_palette[-1] = (255, 0, 255)
                magenta_index = len(rgb_palette) - 1

        # Apply transparency: set transparent pixels to magenta index
        indexed_pixels = list(dithered_img.getdata())
        for i, is_transparent in enumerate(transparency_mask):
            if is_transparent:
                indexed_pixels[i] = magenta_index

        return indexed_pixels, rgb_palette, dithered_img.size

    def rgb_to_bgr555(self, r, g, b):
        """Convert RGB888 to BGR555"""
        r5 = (r * 31) // 255
        g5 = (g * 31) // 255
        b5 = (b * 31) // 255
        return (b5 << 10) | (g5 << 5) | r5

    def encode_image_data(self, pixels, width, height, encoding):
        """Encode pixel data to I8 or I4 format"""
        if encoding == "I8":
            return bytes(pixels[:width * height])
        else:  # I4
            encoded = bytearray()
            for i in range(0, len(pixels), 2):
                if i + 1 < len(pixels):
                    # Two 4-bit pixels in one byte (LSB first)
                    byte = (pixels[i] & 0x0F) | ((pixels[i + 1] & 0x0F) << 4)
                else:
                    byte = pixels[i] & 0x0F
                encoded.append(byte)
            return bytes(encoded)

    def create_5tx_header(self, width, height, encoding, palette_size):
        """Create 5TX file header structure"""
        # NTTX header
        header = b'NTTX'  # Magic
        header += b'\xFF\xFE\x00\x01'  # Unknown but consistent

        # Size field (differs between I8 and I4)
        if encoding == "I8":
            header += struct.pack('<I', 0x4230)  # I8 identifier
        else:
            header += struct.pack('<I', 0x2050)  # I4 identifier

        header += struct.pack('<HH', 0x10, 0x02)  # Unknown but consistent

        # PALT header
        header += b'PALT'  # Palette magic

        # CORRECTED: Fixed palette section sizes
        if encoding == "I8":
            header += struct.pack('<I', 0x020C)  # Fixed size for I8 (524 bytes)
        else:
            header += struct.pack('<I', 0x002C)  # Fixed size for I4 (44 bytes)

        header += struct.pack('<I', palette_size)  # Number of colors

        return header

    def create_imge_header(self, width, height, encoding):
        """Create IMGE header structure - FIXED VERSION"""
        header = b'IMGE'

        if encoding == "I8":
            header += b'\x14\x40\x00\x00'  # I8 specific
            header += b'\x04'  # Encoding byte for I8
            header += b'\x04\x04\x00'  # Fixed I8 pattern
            header += struct.pack('<HH', width, height)  # Dimensions
            header += b'\x00\x40\x00\x00'  # I8 ending
        else:
            header += b'\x14\x20\x00\x00'  # I4 specific
            header += b'\x03'  # Encoding byte for I4
            header += b'\x04\x04\x00'  # Fixed I4 pattern
            header += struct.pack('<HH', width, height)  # Dimensions
            header += b'\x00\x20\x00\x00'  # I4 ending

        return header

    def get_padding_bytes(self, encoding):
        """FIXED: No padding between palette and IMGE header"""
        # The original files show NO padding between palette and IMGE header
        return b''

    def convert(self):
        input_file = self.input_var.get()
        output_file = self.output_var.get()

        if not input_file or not output_file:
            messagebox.showerror("Error", "Please select input and output files")
            return

        try:
            self.status_var.set("Loading image...")
            self.root.update()

            # Load and process image
            img = Image.open(input_file)
            max_colors = int(self.colors_var.get())
            encoding = self.encoding_var.get()
            dither = self.dither_var.get()

            self.status_var.set("Converting to indexed colors...")
            self.root.update()

            pixels, palette, (width, height) = self.convert_image_to_indexed(img, max_colors, dither)

            self.status_var.set("Encoding image data...")
            self.root.update()

            # Encode image data
            image_data = self.encode_image_data(pixels, width, height, encoding)

            self.status_var.set("Creating 5TX structure...")
            self.root.update()

            # Create 5TX file structure
            tx_data = bytearray()

            # Main header
            tx_data.extend(self.create_5tx_header(width, height, encoding, len(palette)))

            # Palette data (BGR555)
            for color in palette:
                bgr555 = self.rgb_to_bgr555(*color)
                tx_data.extend(struct.pack('<H', bgr555))

            # FIXED: No padding bytes between palette and IMGE header
            # The padding = self.get_padding_bytes(encoding) is now empty
            padding = self.get_padding_bytes(encoding)
            tx_data.extend(padding)

            # IMGE header
            tx_data.extend(self.create_imge_header(width, height, encoding))

            # Image data
            tx_data.extend(image_data)

            self.status_var.set("Writing file...")
            self.root.update()

            # Write output file
            with open(output_file, 'wb') as f:
                f.write(tx_data)

            # Print file analysis
            self.analyze_5tx_file(tx_data, output_file)

            self.status_var.set("Conversion complete!")
            messagebox.showinfo("Success", f"Successfully converted to {output_file}")

        except Exception as e:
            self.status_var.set("Error occurred")
            messagebox.showerror("Error", f"Conversion failed: {str(e)}")

    def analyze_5tx_file(self, data, filename):
        """Analyze the created 5TX file to verify structure"""
        print(f"\n=== 5TX File Analysis: {filename} ===")
        print(f"Total file size: {len(data)} bytes")

        # Find headers
        palette_start = data.find(b'PALT')
        imge_start = data.find(b'IMGE')

        print(f"PALT header at: 0x{palette_start:04X}")
        print(f"IMGE header at: 0x{imge_start:04X}")

        # Parse palette info
        palette_colors = struct.unpack_from('<I', data, palette_start + 8)[0]
        print(f"Palette colors: {palette_colors}")

        # Parse image info
        width, height = struct.unpack_from('<HH', data, imge_start + 12)
        encoding_byte = data[imge_start + 8]
        encoding = 'I8' if encoding_byte == 0x04 else 'I4'

        print(f"Image dimensions: {width} x {height}")
        print(f"Encoding: {encoding} (byte: 0x{encoding_byte:02X})")

        # Calculate offsets
        palette_data_start = palette_start + 12
        palette_data_end = palette_data_start + (palette_colors * 2)
        padding_start = palette_data_end
        padding_end = imge_start
        image_data_start = imge_start + 20

        print(f"Palette data: 0x{palette_data_start:04X} - 0x{palette_data_end:04X}")
        print(f"Padding: 0x{padding_start:04X} - 0x{padding_end:04X} ({padding_end - padding_start} bytes)")
        print(f"Image data: 0x{image_data_start:04X} - end")

        # Verify file size matches original structure
        expected_size = image_data_start + (width * height // (2 if encoding == 'I4' else 1))
        print(f"Expected size: {expected_size} bytes")
        print(f"Actual size: {len(data)} bytes")
        print(f"Size match: {len(data) == expected_size}")
        print("====================================\n")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    encoder = FiveTXEncoder()
    encoder.run()