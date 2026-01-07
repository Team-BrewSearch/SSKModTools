import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import struct
from pathlib import Path
import threading
import time
import hashlib
from dataclasses import dataclass
from typing import List, Dict, Optional, BinaryIO
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class FileEntry:
    name: str
    offset: int
    size: int
    file_type: str
    data_file: str
    checksum: str = ""
    modified: bool = False
    new_data: bytes = None


class GDAArchiveManager:
    def __init__(self, root):
        self.root = root
        self.root.title("GDA Archive Manager - Generator Rex: Agent of Providence")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 600)

        # Application state
        self.current_archive = None
        self.archive_type = None  # 'three_file' or 'single'
        self.file_entries: List[FileEntry] = []
        self.modified = False
        self.original_checksums = {}

        # Threading
        self.worker_thread = None
        self.stop_worker = threading.Event()

        # Performance optimization
        self._file_cache = {}
        self._max_cache_size = 100

        # Initialize UI
        self.setup_ui()
        self.setup_bindings()

        # Status
        self.update_status("Ready - No archive loaded")

    def setup_ui(self):
        """Setup the user interface with modern styling"""
        # Configure style
        self.style = ttk.Style()
        self.style.configure('TButton', padding=6)
        self.style.configure('Title.TLabel', font=('Arial', 16, 'bold'))
        self.style.configure('Status.TLabel', background='light gray')

        # Main container
        main_container = ttk.Frame(self.root, padding="10")
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(2, weight=1)

        # Header
        self.setup_header(main_container)

        # Control panel
        self.setup_control_panel(main_container)

        # Search panel
        self.setup_search_panel(main_container)

        # File list
        self.setup_file_list(main_container)

        # Status and progress
        self.setup_status_bar(main_container)

    def setup_header(self, parent):
        """Setup application header"""
        header_frame = ttk.Frame(parent)
        header_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(header_frame, text="GDA Archive Manager", style='Title.TLabel').pack(side=tk.LEFT)

        # Archive info
        self.archive_info = ttk.Label(header_frame, text="No archive loaded", foreground='gray')
        self.archive_info.pack(side=tk.RIGHT)

    def setup_control_panel(self, parent):
        """Setup control buttons panel"""
        controls_frame = ttk.LabelFrame(parent, text="Archive Operations", padding="10")
        controls_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        # Button grid
        button_configs = [
            ("Open Archive", self.open_archive, "Open GDA/GDF/GDT archive"),
            ("Extract Selected", self.extract_selected, "Extract selected files"),
            ("Extract All", self.extract_all, "Extract all files with folder structure"),
            ("Replace File", self.replace_file, "Replace selected file with external file"),
            ("Add File", self.add_file, "Add new file to archive"),
            ("Delete File", self.delete_file, "Remove selected file from archive"),
            ("Save Archive", self.save_archive, "Save modified archive"),
            ("Save As", self.save_archive_as, "Save archive with new name"),
        ]

        for i, (text, command, tooltip) in enumerate(button_configs):
            btn = ttk.Button(controls_frame, text=text, command=command)
            btn.grid(row=i // 4, column=i % 4, padx=5, pady=2, sticky=tk.W + tk.E)
            self.create_tooltip(btn, tooltip)

        # Configure grid weights for even button distribution
        for i in range(4):
            controls_frame.columnconfigure(i, weight=1)

    def setup_search_panel(self, parent):
        """Setup search and filter panel"""
        search_frame = ttk.Frame(parent)
        search_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        ttk.Button(search_frame, text="Clear", command=self.clear_search).pack(side=tk.LEFT, padx=5)

        # File type filter
        ttk.Label(search_frame, text="Type:").pack(side=tk.LEFT, padx=(20, 5))
        self.type_var = tk.StringVar(value="All")
        type_combo = ttk.Combobox(search_frame, textvariable=self.type_var,
                                  values=["All", "Texture", "Binary", "Archive", "Text", "Image", "XML", "JSON"],
                                  state="readonly", width=12)
        type_combo.pack(side=tk.LEFT, padx=5)
        type_combo.bind('<<ComboboxSelected>>', self.filter_files)

    def setup_file_list(self, parent):
        """Setup file list with treeview"""
        list_frame = ttk.LabelFrame(parent, text="Archive Contents", padding="5")
        list_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        # Create treeview with better styling
        columns = ('name', 'size', 'offset', 'type', 'status')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', selectmode='extended')

        # Define headings with sorting
        self.tree.heading('name', text='File Name',
                          command=lambda: self.sort_treeview('name', False))
        self.tree.heading('size', text='Size',
                          command=lambda: self.sort_treeview('size', False))
        self.tree.heading('offset', text='Offset',
                          command=lambda: self.sort_treeview('offset', False))
        self.tree.heading('type', text='Type',
                          command=lambda: self.sort_treeview('type', False))
        self.tree.heading('status', text='Status',
                          command=lambda: self.sort_treeview('status', False))

        # Define columns
        self.tree.column('name', width=400, minwidth=200)
        self.tree.column('size', width=100, minwidth=80)
        self.tree.column('offset', width=120, minwidth=80)
        self.tree.column('type', width=100, minwidth=80)
        self.tree.column('status', width=80, minwidth=60)

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        # Grid layout
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        h_scrollbar.grid(row=1, column=0, sticky=(tk.W, tk.E))

        # Context menu
        self.setup_context_menu()

    def setup_context_menu(self):
        """Setup right-click context menu"""
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Extract", command=self.extract_selected)
        self.context_menu.add_command(label="Replace", command=self.replace_file)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="View Properties", command=self.show_properties)

        self.tree.bind("<Button-3>", self.show_context_menu)

    def setup_status_bar(self, parent):
        """Setup status bar and progress indicator"""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))

        # Status label
        self.status_var = tk.StringVar()
        status_label = ttk.Label(status_frame, textvariable=self.status_var,
                                 relief=tk.SUNKEN, style='Status.TLabel', padding=2)
        status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Progress bar
        self.progress = ttk.Progressbar(status_frame, mode='determinate')
        self.progress.pack(side=tk.RIGHT, fill=tk.X, padx=(5, 0))

        # File count
        self.file_count_var = tk.StringVar(value="Files: 0")
        file_count_label = ttk.Label(status_frame, textvariable=self.file_count_var, padding=2)
        file_count_label.pack(side=tk.RIGHT, padx=(5, 0))

    def setup_bindings(self):
        """Setup keyboard and mouse bindings"""
        self.root.bind('<Control-o>', lambda e: self.open_archive())
        self.root.bind('<Control-s>', lambda e: self.save_archive())
        self.root.bind('<Control-a>', lambda e: self.select_all())
        self.root.bind('<Delete>', lambda e: self.delete_file())
        self.root.bind('<F5>', lambda e: self.refresh_list())

        self.search_entry.bind('<KeyRelease>', self.filter_files)
        self.tree.bind('<Double-1>', self.on_double_click)
        self.tree.bind('<<TreeviewSelect>>', self.on_selection_change)

    def create_tooltip(self, widget, text):
        """Create tooltip for widgets"""

        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
            label = ttk.Label(tooltip, text=text, background="lightyellow",
                              relief='solid', borderwidth=1, padding=2)
            label.pack()
            widget.tooltip = tooltip

        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    # Core Archive Operations
    def open_archive(self, file_path=None):
        """Open archive file(s)"""
        if not file_path:
            file_path = filedialog.askopenfilename(
                title="Select GDA, GDF, or GDT file",
                filetypes=[
                    ("Archive files", "*.gda *.gdf *.gdt"),
                    ("GDA files", "*.gda"),
                    ("GDF files", "*.gdf"),
                    ("GDT files", "*.gdt"),
                    ("All files", "*.*")
                ]
            )

        if file_path:
            self.stop_worker.set()  # Stop any running operations
            if self.worker_thread and self.worker_thread.is_alive():
                self.worker_thread.join(timeout=1.0)

            self.current_archive = file_path
            self.modified = False
            self._file_cache.clear()
            self.update_status(f"Loading archive: {os.path.basename(file_path)}")

            self.worker_thread = threading.Thread(target=self.load_archive_thread,
                                                  args=(file_path,), daemon=True)
            self.worker_thread.start()

    def load_archive_thread(self, file_path):
        """Threaded archive loading"""
        try:
            self.progress['value'] = 0
            self.root.update_idletasks()

            base_path = os.path.splitext(file_path)[0]
            gdt_path = base_path + '.gdt'
            gdf_path = base_path + '.gdf'
            gda_path = base_path + '.gda'

            # Determine archive type
            files_exist = {
                'gdt': os.path.exists(gdt_path),
                'gdf': os.path.exists(gdf_path),
                'gda': os.path.exists(gda_path)
            }

            self.file_entries.clear()
            self.original_checksums.clear()

            if files_exist['gdt'] and files_exist['gdf'] and files_exist['gda']:
                self.archive_type = 'three_file'
                self.parse_three_file_archive(gdt_path, gdf_path, gda_path)
            else:
                self.archive_type = 'single'
                self.parse_single_file(file_path)

            # Calculate checksums for change detection
            for entry in self.file_entries:
                self.original_checksums[entry.name] = self.calculate_file_checksum(entry)

            self.root.after(0, self.on_archive_loaded)

        except Exception as e:
            logger.error(f"Error loading archive: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to load archive: {str(e)}"))
            self.root.after(0, lambda: self.update_status("Error loading archive"))

    def parse_three_file_archive(self, gdt_path, gdf_path, gda_path):
        """Parse three-file archive format"""
        with open(gdt_path, 'rb') as gdt_file, \
                open(gdf_path, 'rb') as gdf_file, \
                open(gda_path, 'rb') as gda_file:

            # Read GDT (file index)
            zero = struct.unpack('<I', gdt_file.read(4))[0]
            files_count = struct.unpack('<I', gdt_file.read(4))[0]

            # Read GDF (names index)
            files_count_gdf = struct.unpack('<I', gdf_file.read(4))[0]
            if files_count != files_count_gdf:
                logger.warning(f"File count mismatch: GDT={files_count}, GDF={files_count_gdf}")

            names_offset = 4 + (files_count_gdf * 4)

            # Read file entries
            file_entries = []
            for i in range(files_count):
                offset = struct.unpack('<I', gdt_file.read(4))[0]
                size = struct.unpack('<I', gdt_file.read(4))[0]
                file_entries.append((offset, size))

            # Read file names
            for i, (offset, size) in enumerate(file_entries):
                name_offset = struct.unpack('<I', gdf_file.read(4))[0]
                current_pos = gdf_file.tell()

                gdf_file.seek(names_offset + name_offset)
                name_bytes = bytearray()
                while True:
                    byte = gdf_file.read(1)
                    if byte == b'\x00' or not byte:
                        break
                    name_bytes.extend(byte)

                try:
                    name = name_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    name = name_bytes.decode('latin-1')

                gdf_file.seek(current_pos)

                # Verify file exists in GDA
                gda_file.seek(offset)
                if offset + size > os.path.getsize(gda_path):
                    logger.warning(f"File {name} exceeds GDA bounds, skipping")
                    continue

                entry = FileEntry(
                    name=name,
                    offset=offset,
                    size=size,
                    file_type=self.get_file_type(name),
                    data_file=gda_path
                )
                self.file_entries.append(entry)

                # Update progress
                if i % 10 == 0:
                    progress = (i / files_count) * 100
                    self.root.after(0, lambda p=progress: self.progress.config(value=p))

    def parse_single_file(self, file_path):
        """Parse single archive file"""
        try:
            file_size = os.path.getsize(file_path)
            entry = FileEntry(
                name=os.path.basename(file_path),
                offset=0,
                size=file_size,
                file_type=self.get_file_type(file_path),
                data_file=file_path
            )
            self.file_entries.append(entry)

        except Exception as e:
            raise Exception(f"Failed to parse single file: {str(e)}")

    def calculate_file_checksum(self, file_entry: FileEntry) -> str:
        """Calculate checksum for file verification"""
        try:
            with open(file_entry.data_file, 'rb') as f:
                f.seek(file_entry.offset)
                data = f.read(file_entry.size)
                return hashlib.md5(data).hexdigest()
        except:
            return ""

    def get_file_type(self, filename: str) -> str:
        """Determine file type from extension"""
        ext = os.path.splitext(filename)[1].lower()
        type_map = {
            '.txt': 'Text', '.xml': 'XML', '.json': 'JSON', '.ini': 'Config',
            '.dds': 'Texture', '.tga': 'Texture', '.png': 'Image', '.jpg': 'Image',
            '.gda': 'Archive', '.gdf': 'Archive', '.gdt': 'Archive',
            '.bin': 'Binary', '.dat': 'Data', '.exe': 'Executable', '.dll': 'Library'
        }
        return type_map.get(ext, 'Unknown')

    def on_archive_loaded(self):
        """Callback when archive is successfully loaded"""
        self.update_file_list()
        self.progress['value'] = 100
        archive_name = os.path.basename(self.current_archive)
        self.archive_info.config(text=f"Loaded: {archive_name} ({len(self.file_entries)} files)")
        self.update_status(f"Successfully loaded {len(self.file_entries)} files")
        self.update_window_title()

    def update_file_list(self):
        """Update treeview with file data"""
        self.tree.delete(*self.tree.get_children())

        for entry in self.file_entries:
            status = "Modified" if entry.modified else "Original"
            self.tree.insert('', 'end', values=(
                entry.name,
                self.format_size(entry.size),
                f"0x{entry.offset:08X}",
                entry.file_type,
                status
            ), tags=('modified' if entry.modified else 'original'))

        # Configure tags for color coding
        self.tree.tag_configure('modified', foreground='red')
        self.tree.tag_configure('original', foreground='black')

        self.file_count_var.set(f"Files: {len(self.file_entries)}")

    def format_size(self, size: int) -> str:
        """Format file size for display"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    # File Operations
    def extract_selected(self):
        """Extract selected files"""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "No files selected for extraction")
            return

        output_dir = filedialog.askdirectory(title="Select output directory")
        if not output_dir:
            return

        file_entries = []
        for item in selected_items:
            filename = self.tree.item(item)['values'][0]
            entry = next((e for e in self.file_entries if e.name == filename), None)
            if entry:
                file_entries.append(entry)

        threading.Thread(target=self._extract_files_thread,
                         args=(file_entries, output_dir), daemon=True).start()

    def extract_all(self):
        """Extract all files"""
        if not self.file_entries:
            messagebox.showwarning("Warning", "No files to extract")
            return

        output_dir = filedialog.askdirectory(title="Select output directory")
        if not output_dir:
            return

        threading.Thread(target=self._extract_files_thread,
                         args=(self.file_entries, output_dir), daemon=True).start()

    def _extract_files_thread(self, file_entries: List[FileEntry], output_dir: str):
        """Threaded file extraction"""
        try:
            total_files = len(file_entries)
            success_count = 0

            with ThreadPoolExecutor(max_workers=4) as executor:
                future_to_entry = {
                    executor.submit(self.extract_single_file, entry, output_dir): entry
                    for entry in file_entries
                }

                for i, future in enumerate(as_completed(future_to_entry)):
                    entry = future_to_entry[future]
                    try:
                        future.result()
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to extract {entry.name}: {e}")

                    progress = ((i + 1) / total_files) * 100
                    self.root.after(0, lambda p=progress: self.progress.config(value=p))
                    self.root.after(0, lambda: self.update_status(
                        f"Extracting: {entry.name} ({i + 1}/{total_files})"))

            self.root.after(0, lambda: self.progress.config(value=0))
            self.root.after(0, lambda: self.update_status(
                f"Extraction complete: {success_count}/{total_files} files"))

            if success_count == total_files:
                self.root.after(0, lambda: messagebox.showinfo("Success",
                                                               f"Successfully extracted {success_count} files"))
            else:
                self.root.after(0, lambda: messagebox.showwarning("Partial Success",
                                                                  f"Extracted {success_count} out of {total_files} files"))

        except Exception as e:
            logger.error(f"Extraction thread error: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Extraction failed: {str(e)}"))

    def extract_single_file(self, file_entry: FileEntry, output_dir: str):
        """Extract a single file with proper path handling"""
        output_path = os.path.join(output_dir, file_entry.name)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            if file_entry.modified and file_entry.new_data is not None:
                # Use modified data
                with open(output_path, 'wb') as output_file:
                    output_file.write(file_entry.new_data)
            else:
                # Read from original archive
                with open(file_entry.data_file, 'rb') as data_file:
                    data_file.seek(file_entry.offset)
                    file_data = data_file.read(file_entry.size)
                    with open(output_path, 'wb') as output_file:
                        output_file.write(file_data)
        except Exception as e:
            raise Exception(f"Failed to extract {file_entry.name}: {str(e)}")

    def replace_file(self):
        """Replace selected file with external file"""
        selected_items = self.tree.selection()
        if not selected_items or len(selected_items) != 1:
            messagebox.showwarning("Warning", "Please select exactly one file to replace")
            return

        item = selected_items[0]
        filename = self.tree.item(item)['values'][0]
        file_entry = next((e for e in self.file_entries if e.name == filename), None)

        if not file_entry:
            messagebox.showerror("Error", "Selected file not found in archive")
            return

        new_file = filedialog.askopenfilename(title=f"Select replacement file for {filename}")
        if not new_file:
            return

        try:
            with open(new_file, 'rb') as f:
                new_data = f.read()

            # Update file entry
            file_entry.new_data = new_data
            file_entry.size = len(new_data)
            file_entry.modified = True

            self.modified = True
            self.update_file_list()
            self.update_window_title()
            self.update_status(f"File {filename} marked for replacement")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to read replacement file: {str(e)}")

    def add_file(self):
        """Add new file to archive"""
        new_file = filedialog.askopenfilename(title="Select file to add to archive")
        if not new_file:
            return

        # Ask for virtual path in archive
        virtual_path = tk.simpledialog.askstring("Add File",
                                                 "Enter virtual path in archive (e.g., textures/new_file.dds):",
                                                 initialvalue=os.path.basename(new_file))

        if not virtual_path:
            return

        try:
            with open(new_file, 'rb') as f:
                new_data = f.read()

            new_entry = FileEntry(
                name=virtual_path,
                offset=0,  # Will be calculated on save
                size=len(new_data),
                file_type=self.get_file_type(virtual_path),
                data_file="",  # No original data file
                new_data=new_data,
                modified=True
            )

            self.file_entries.append(new_entry)
            self.modified = True
            self.update_file_list()
            self.update_window_title()
            self.update_status(f"Added {virtual_path} to archive")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to add file: {str(e)}")

    def delete_file(self):
        """Remove selected file from archive"""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "No files selected for deletion")
            return

        filenames = [self.tree.item(item)['values'][0] for item in selected_items]
        confirm = messagebox.askyesno("Confirm Delete",
                                      f"Are you sure you want to delete {len(filenames)} file(s)?\n\n" +
                                      "\n".join(f"- {name}" for name in filenames[:5]) +
                                      ("\n..." if len(filenames) > 5 else ""))

        if not confirm:
            return

        # Mark files for deletion
        for filename in filenames:
            file_entry = next((e for e in self.file_entries if e.name == filename), None)
            if file_entry:
                file_entry.modified = True
                file_entry.new_data = None  # None data indicates deletion

        self.modified = True
        self.update_file_list()
        self.update_window_title()
        self.update_status(f"Marked {len(filenames)} file(s) for deletion")

    # Archive Saving
    def save_archive(self):
        """Save archive with current modifications"""
        if not self.modified:
            messagebox.showinfo("Info", "No changes to save")
            return

        if not self.current_archive:
            self.save_archive_as()
            return

        if self.archive_type == 'three_file':
            base_path = os.path.splitext(self.current_archive)[0]
            self.save_three_file_archive(base_path + '.gdt', base_path + '.gdf', base_path + '.gda')
        else:
            self.save_single_archive(self.current_archive)

    def save_archive_as(self):
        """Save archive with new filename"""
        if self.archive_type == 'three_file':
            base_path = filedialog.asksaveasfilename(
                title="Save Archive As",
                defaultextension=".gdt",
                filetypes=[("GDT files", "*.gdt")]
            )
            if base_path:
                base_path = os.path.splitext(base_path)[0]
                self.save_three_file_archive(base_path + '.gdt', base_path + '.gdf', base_path + '.gda')
        else:
            file_path = filedialog.asksaveasfilename(
                title="Save Archive As",
                defaultextension=".gda",
                filetypes=[("GDA files", "*.gda")]
            )
            if file_path:
                self.save_single_archive(file_path)

    def save_three_file_archive(self, gdt_path: str, gdf_path: str, gda_path: str):
        """Save three-file archive format"""
        try:
            # Filter out deleted files and prepare data
            active_entries = [entry for entry in self.file_entries
                              if not (entry.modified and entry.new_data is None)]

            # Build GDA file data
            current_offset = 0
            gda_data = bytearray()
            file_entries_updated = []

            for entry in active_entries:
                if entry.modified and entry.new_data is not None:
                    data = entry.new_data
                else:
                    with open(entry.data_file, 'rb') as f:
                        f.seek(entry.offset)
                        data = f.read(entry.size)

                gda_data.extend(data)
                file_entries_updated.append((entry.name, current_offset, len(data)))
                current_offset += len(data)

            # Write GDA file
            with open(gda_path, 'wb') as f:
                f.write(gda_data)

            # Build GDF file (names)
            name_table = bytearray()
            name_offsets = []
            current_name_offset = 0

            for name, _, _ in file_entries_updated:
                name_encoded = name.encode('utf-8') + b'\x00'
                name_offsets.append(current_name_offset)
                name_table.extend(name_encoded)
                current_name_offset += len(name_encoded)

            # Write GDF file
            with open(gdf_path, 'wb') as f:
                f.write(struct.pack('<I', len(file_entries_updated)))  # File count
                for offset in name_offsets:
                    f.write(struct.pack('<I', offset))
                f.write(name_table)

            # Write GDT file
            with open(gdt_path, 'wb') as f:
                f.write(struct.pack('<I', 0))  # Zero field
                f.write(struct.pack('<I', len(file_entries_updated)))  # File count
                for _, offset, size in file_entries_updated:
                    f.write(struct.pack('<I', offset))
                    f.write(struct.pack('<I', size))

            # Update state
            self.modified = False
            self.current_archive = gdt_path
            self.update_status("Archive saved successfully")
            self.update_window_title()
            messagebox.showinfo("Success", "Archive saved successfully")

        except Exception as e:
            logger.error(f"Error saving archive: {e}")
            messagebox.showerror("Error", f"Failed to save archive: {str(e)}")

    def save_single_archive(self, file_path: str):
        """Save single file archive"""
        # Implementation for single file archives
        messagebox.showinfo("Info", "Single file archive saving not fully implemented yet")

    # UI Helpers
    def update_status(self, message: str):
        """Update status bar message"""
        self.status_var.set(message)
        logger.info(message)

    def update_window_title(self):
        """Update window title with modification indicator"""
        base_title = "GDA Archive Manager - Generator Rex: Agent of Providence"
        if self.current_archive:
            archive_name = os.path.basename(self.current_archive)
            mod_indicator = " *" if self.modified else ""
            self.root.title(f"{archive_name}{mod_indicator} - {base_title}")
        else:
            self.root.title(base_title)

    def filter_files(self, event=None):
        """Filter files based on search criteria"""
        search_text = self.search_var.get().lower()
        type_filter = self.type_var.get()

        self.tree.delete(*self.tree.get_children())

        for entry in self.file_entries:
            # Apply filters
            if search_text and search_text not in entry.name.lower():
                continue
            if type_filter != "All" and type_filter != entry.file_type:
                continue

            status = "Modified" if entry.modified else "Original"
            self.tree.insert('', 'end', values=(
                entry.name,
                self.format_size(entry.size),
                f"0x{entry.offset:08X}",
                entry.file_type,
                status
            ), tags=('modified' if entry.modified else 'original'))

    def clear_search(self):
        """Clear search and filter"""
        self.search_var.set("")
        self.type_var.set("All")
        self.filter_files()

    def sort_treeview(self, column, reverse):
        """Sort treeview by column"""
        data = [(self.tree.set(child, column), child) for child in self.tree.get_children('')]

        try:
            if column == 'size':
                data.sort(key=lambda x: self.parse_size(x[0]), reverse=reverse)
            elif column == 'offset':
                data.sort(key=lambda x: int(x[0].replace('0x', ''), 16), reverse=reverse)
            else:
                data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        except:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)

        for index, (_, child) in enumerate(data):
            self.tree.move(child, '', index)

        self.tree.heading(column, command=lambda: self.sort_treeview(column, not reverse))

    def parse_size(self, size_str: str) -> int:
        """Parse size string back to bytes"""
        units = {'B': 1, 'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3}
        for unit, multiplier in units.items():
            if size_str.endswith(unit):
                return int(float(size_str.replace(unit, '').strip()) * multiplier)
        return 0

    def on_double_click(self, event):
        """Handle double-click for quick extraction"""
        item = self.tree.identify('item', event.x, event.y)
        if item:
            output_dir = filedialog.askdirectory(title="Select output directory for single file")
            if output_dir:
                filename = self.tree.item(item)['values'][0]
                file_entry = next((e for e in self.file_entries if e.name == filename), None)
                if file_entry:
                    threading.Thread(target=self._extract_single_thread,
                                     args=(file_entry, output_dir), daemon=True).start()

    def _extract_single_thread(self, file_entry: FileEntry, output_dir: str):
        """Threaded single file extraction"""
        try:
            self.extract_single_file(file_entry, output_dir)
            self.root.after(0, lambda: messagebox.showinfo("Success", f"Extracted: {file_entry.name}"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Extraction failed: {str(e)}"))

    def on_selection_change(self, event):
        """Handle selection change"""
        selected_count = len(self.tree.selection())
        self.update_status(f"{selected_count} file(s) selected")

    def show_context_menu(self, event):
        """Show right-click context menu"""
        item = self.tree.identify('item', event.x, event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def show_properties(self):
        """Show properties of selected file"""
        selected_items = self.tree.selection()
        if not selected_items or len(selected_items) != 1:
            return

        item = selected_items[0]
        filename = self.tree.item(item)['values'][0]
        file_entry = next((e for e in self.file_entries if e.name == filename), None)

        if file_entry:
            properties = f"""
File Properties:

Name: {file_entry.name}
Type: {file_entry.file_type}
Size: {self.format_size(file_entry.size)} ({file_entry.size} bytes)
Offset: 0x{file_entry.offset:08X}
Data File: {file_entry.data_file}
Status: {'Modified' if file_entry.modified else 'Original'}
Checksum: {self.calculate_file_checksum(file_entry)}
"""
            messagebox.showinfo("File Properties", properties.strip())

    def select_all(self):
        """Select all files in the list"""
        self.tree.selection_set(self.tree.get_children())

    def refresh_list(self):
        """Refresh file list"""
        if self.current_archive:
            self.open_archive(self.current_archive)

    def cleanup(self):
        """Cleanup resources before exit"""
        self.stop_worker.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)


def main():
    """Main application entry point"""
    try:
        root = tk.Tk()
        app = GDAArchiveManager(root)

        # Handle window close
        root.protocol("WM_DELETE_WINDOW", lambda: (app.cleanup(), root.destroy()))

        # Center window
        root.update_idletasks()
        x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
        y = (root.winfo_screenheight() - root.winfo_reqheight()) // 2
        root.geometry(f"+{x}+{y}")

        root.mainloop()

    except Exception as e:
        logger.critical(f"Application crash: {e}")
        messagebox.showerror("Fatal Error", f"The application encountered a fatal error:\n\n{str(e)}")


if __name__ == "__main__":
    main()