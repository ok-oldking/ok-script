import json
import os
from typing import TypedDict

import cv2
from PySide6.QtCore import Qt, Signal, QTimer, QRunnable, QThreadPool, QObject
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QScrollArea, QLabel, QFrame)
from qfluentwidgets import (PushButton, PrimaryPushButton, FluentIcon,
                            SearchLineEdit, MessageBox, BodyLabel, isDarkTheme,
                            qconfig, IndeterminateProgressRing)

from ok import Config, og
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

TEMPLATE_FOLDER = 'ok_templates'
COCO_JSON = 'coco_annotations.json'
THUMB_SIZE = 160
CARD_WIDTH = THUMB_SIZE + 16
CARD_HEIGHT = THUMB_SIZE + 40
GRID_SPACING = 8


class ImageDict(TypedDict):
    id: int
    file_name: str
    width: int
    height: int


class AnnotationDict(TypedDict):
    id: int
    image_id: int
    category_id: int
    bbox: list[float]  # [x, y, w, h]
    area: float
    iscrowd: int


class CategoryDict(TypedDict):
    id: int
    name: str
    supercategory: str


class CocoData(TypedDict):
    images: list[ImageDict]
    annotations: list[AnnotationDict]
    categories: list[CategoryDict]


def ensure_template_folder():
    folder = os.path.join(os.getcwd(), TEMPLATE_FOLDER)
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
    return folder


def get_coco_path():
    return os.path.join(ensure_template_folder(), COCO_JSON)


def load_coco() -> CocoData:
    path = get_coco_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load COCO json: {e}")
    return {
        "images": [],
        "annotations": [],
        "categories": []
    }


def save_coco(coco_data):
    path = get_coco_path()
    coco_data['annotations'].sort(key=lambda x: x['id'])
    coco_data['categories'].sort(key=lambda x: x['id'])
    coco_data['images'].sort(key=lambda x: x['id'])
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(coco_data, f, indent=2, ensure_ascii=False)


def get_image_files():
    """Get all image files sorted by creation time descending."""
    folder = ensure_template_folder()
    exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
    files = []
    for f in os.listdir(folder):
        if os.path.splitext(f)[1].lower() in exts:
            full = os.path.join(folder, f)
            files.append((full, os.path.getctime(full)))
    files.sort(key=lambda x: x[1], reverse=True)
    return [f[0] for f in files]


def get_next_image_name(folder):
    """Find the next available numeric image name."""
    existing = set()
    for f in os.listdir(folder):
        name = os.path.splitext(f)[0]
        if name.isdigit():
            existing.add(int(name))
    i = 0
    while i in existing:
        i += 1
    return str(i)


def get_categories_for_image(coco_data, image_path):
    """Get category names associated with an image."""
    filename = os.path.basename(image_path)
    image_id = None
    for img in coco_data.get('images', []):
        if img['file_name'] == filename:
            image_id = img['id']
            break
    if image_id is None:
        return []
    cat_ids = set()
    for ann in coco_data.get('annotations', []):
        if ann['image_id'] == image_id:
            cat_ids.add(ann['category_id'])
    cat_names = []
    for cat in coco_data.get('categories', []):
        if cat['id'] in cat_ids:
            cat_names.append(cat['name'])
    return cat_names


def _card_style(selected, dark):
    """Return card stylesheet based on selection state and theme."""
    if selected:
        return """
            ImageCard {
                border: 2px solid #0078d4;
                border-radius: 8px;
                background-color: rgba(0, 120, 212, 0.15);
            }
        """
    if dark:
        return """
            ImageCard {
                border: 1px solid rgba(200, 200, 200, 0.15);
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 0.04);
            }
            ImageCard:hover {
                border: 1px solid rgba(0, 120, 212, 0.6);
                background-color: rgba(255, 255, 255, 0.08);
            }
        """
    return """
        ImageCard {
            border: 1px solid rgba(0, 0, 0, 0.12);
            border-radius: 8px;
            background-color: transparent;
        }
        ImageCard:hover {
            border: 1px solid rgba(0, 120, 212, 0.5);
            background-color: rgba(0, 120, 212, 0.05);
        }
    """


class ImageLoaderSignals(QObject):
    finished = Signal(list, int)

class ImageLoaderRunnable(QRunnable):
    def __init__(self, coco_data, query, seq):
        super().__init__()
        self.coco_data = coco_data
        self.query = query
        self.seq = seq
        self.signals = ImageLoaderSignals()

    def run(self):
        try:
            all_images = get_image_files()
            
            if self.query:
                filtered = []
                for img_path in all_images:
                    name = os.path.splitext(os.path.basename(img_path))[0].lower()
                    cats = get_categories_for_image(self.coco_data, img_path)
                    cat_str = ' '.join(cats).lower()
                    if self.query in name or self.query in cat_str:
                        filtered.append(img_path)
                all_images = filtered

            results = []
            for img_path in all_images:
                cats = get_categories_for_image(self.coco_data, img_path)
                cats_str = ', '.join(cats)
                qimg = QImage(img_path)
                if not qimg.isNull():
                    scaled = qimg.scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    results.append((img_path, scaled, cats_str))
                else:
                    results.append((img_path, None, cats_str))
            
            logger.info(f"Image search finished, found {len(results)} items.")
            self.signals.finished.emit(results, self.seq)
        except Exception as e:
            logger.error(f"Image search failed: {e}", exc_info=True)
            self.signals.finished.emit([], self.seq)


class ImageCard(QFrame):
    clicked = Signal(str)
    double_clicked = Signal(str)

    def __init__(self, image_path, parent=None, preloaded_image=None, features_text=""):
        super().__init__(parent)
        self.image_path = image_path
        self.selected = False
        self.original_thumb = preloaded_image
        self._features_text_full = features_text
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        self.features_label = BodyLabel()
        self.features_label.setAlignment(Qt.AlignCenter)
        self.features_label.setWordWrap(True)

        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignCenter)

        self.name_label = BodyLabel(os.path.splitext(os.path.basename(image_path))[0])
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)

        layout.addWidget(self.features_label)
        layout.addWidget(self.thumb_label)
        layout.addWidget(self.name_label)

        self._apply_style()
        self.set_card_width(CARD_WIDTH)

    def set_card_width(self, w):
        thumb_size = w - 16
        metrics = self.fontMetrics()
        lh = metrics.lineSpacing()
        
        f_h = lh * 3 if self._features_text_full else 0
        name_h = lh * 2
        
        self.features_label.setFixedHeight(f_h)
        self.name_label.setFixedHeight(name_h)
        
        total_h = thumb_size + f_h + name_h + 12
        self.setFixedSize(w, total_h)

        self.thumb_label.setFixedSize(thumb_size, thumb_size)
        if self.original_thumb is not None and not self.original_thumb.isNull():
            scaled = self.original_thumb.scaled(thumb_size, thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumb_label.setPixmap(QPixmap.fromImage(scaled))
        else:
            pixmap = QPixmap(self.image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(thumb_size, thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumb_label.setPixmap(scaled)

        self.features_label.setText(self._features_text_full)

    def set_selected(self, selected):
        self.selected = selected
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(_card_style(self.selected, isDarkTheme()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.image_path)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.image_path)
        super().mouseDoubleClickEvent(event)


class FlowWidget(QWidget):
    """A widget that lays out children in a left-aligned flow (wrapping rows)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._spacing = GRID_SPACING

    def clear_items(self):
        for w in self._items:
            w.setParent(None)
            w.deleteLater()
        self._items.clear()

    def add_item(self, widget):
        widget.setParent(self)
        self._items.append(widget)
        self._relayout()

    def _relayout(self):
        if not self._items:
            self.setMinimumHeight(0)
            return

        columns = 5
        available_width = max(self.width(), CARD_WIDTH)
        
        # Calculate ideal card width so 5 cards fit perfectly in the available space
        target_card_width = max((available_width - (columns - 1) * self._spacing) // columns, 50)
        
        x = 0
        y = 0
        row_height = 0

        for widget in self._items:
            if hasattr(widget, 'set_card_width'):
                # Only resize if the target is noticeably different to avoid excessive reloading
                if abs(widget.width() - target_card_width) > 1:
                    widget.set_card_width(target_card_width)
            
            w = widget.width()
            h = widget.height()

            # Slight tolerance (+2) for floating/integer precision issues
            if x > 0 and x + w > available_width + 2:
                x = 0
                y += row_height + self._spacing
                row_height = 0

            widget.move(x, y)
            widget.show()

            row_height = max(row_height, h)
            x += w + self._spacing

        total_height = y + row_height
        self.setMinimumHeight(total_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()


class TemplateTab(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.setObjectName("TemplateTab")
        self.template_tab_config = config.get('template_tab', {
            'generate_label_enum': False,
            'label_enum_relative_path': 'ok_tasks/LabelEnum.py'
        })
        self.selected_image = None
        self.image_cards = []
        self.markup_window = None
        self.coco_data = load_coco()
        self._loaded = False
        self._load_sequence = 0
        self.init_ui()

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.refresh_grid)

        # Listen for theme changes
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.refresh_grid()

    def _on_theme_changed(self):
        """Re-apply styles when the theme changes."""
        for card in self.image_cards:
            card._apply_style()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(8)

        # Top toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.screenshot_btn = PrimaryPushButton(FluentIcon.CAMERA, self.tr("Screenshot"))
        self.screenshot_btn.clicked.connect(self.take_screenshot)
        toolbar.addWidget(self.screenshot_btn)

        self.markup_btn = PushButton(FluentIcon.EDIT, self.tr("Markup"))
        self.markup_btn.clicked.connect(self.open_markup)
        self.markup_btn.setVisible(False)
        toolbar.addWidget(self.markup_btn)

        self.delete_btn = PushButton(FluentIcon.DELETE, self.tr("Delete"))
        self.delete_btn.clicked.connect(self.delete_image)
        self.delete_btn.setVisible(False)
        toolbar.addWidget(self.delete_btn)

        self.save_btn = PushButton(FluentIcon.SAVE, self.tr("Save"))
        self.save_btn.clicked.connect(self.save_compressed)
        toolbar.addWidget(self.save_btn)

        toolbar.addStretch(1)
        main_layout.addLayout(toolbar)

        # Search box
        self.search_box = SearchLineEdit()
        self.search_box.setPlaceholderText(self.tr("Search by name or category..."))
        self.search_box.textChanged.connect(self.on_search_changed)
        main_layout.addWidget(self.search_box)

        # Scroll area for flow grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll_area.viewport().setStyleSheet("background: transparent;")

        self.flow_widget = FlowWidget()
        self.flow_widget.setStyleSheet("background: transparent;")
        self.scroll_area.setWidget(self.flow_widget)
        main_layout.addWidget(self.scroll_area, 1)

        # Empty state widget (centered screenshot button)
        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setAlignment(Qt.AlignCenter)

        self.empty_label = BodyLabel(self.tr("No templates yet"))
        self.empty_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_label)

        self.center_screenshot_btn = PrimaryPushButton(FluentIcon.CAMERA, self.tr("Take Screenshot"))
        self.center_screenshot_btn.setFixedWidth(200)
        self.center_screenshot_btn.clicked.connect(self.take_screenshot)
        empty_layout.addWidget(self.center_screenshot_btn, alignment=Qt.AlignCenter)

        main_layout.addWidget(self.empty_widget, 1)
        self.empty_widget.setVisible(False)

        self.progress_ring = IndeterminateProgressRing()
        self.progress_ring.setFixedSize(50, 50)
        self.progress_container = QWidget()
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.progress_ring, alignment=Qt.AlignCenter)
        main_layout.addWidget(self.progress_container, 1)
        self.progress_container.setVisible(False)

    def refresh_grid(self):
        """Reload image files and repopulate the grid."""
        query = self.search_box.text().strip().lower() if hasattr(self, 'search_box') else ""
        logger.info(f"Refreshing grid with query: '{query}'")
        self.coco_data = load_coco()

        # Clear existing cards
        self.image_cards.clear()
        self.flow_widget.clear_items()

        self.scroll_area.setVisible(False)
        self.empty_widget.setVisible(False)
        self.progress_container.setVisible(True)
        
        if hasattr(self, 'search_box'):
            self.search_box.setEnabled(False)
            
        self.progress_ring.start()

        self._load_sequence += 1
        current_seq = self._load_sequence
        
        runnable = ImageLoaderRunnable(self.coco_data, query, current_seq)
        runnable.signals.finished.connect(self._on_load_finished)
        QThreadPool.globalInstance().start(runnable)

    def _on_load_finished(self, items, seq):
        if seq != getattr(self, '_load_sequence', 0):
            return

        self.progress_ring.stop()
        self.progress_container.setVisible(False)
        
        if hasattr(self, 'search_box'):
            self.search_box.setEnabled(True)

        if not items:
            self.empty_widget.setVisible(True)
            self.selected_image = None
            self._update_selection_buttons()
            return

        self.scroll_area.setVisible(True)

        all_images = []
        for img_path, scaled_img, cats_str in items:
            all_images.append(img_path)
            card = ImageCard(img_path, preloaded_image=scaled_img, features_text=cats_str)
            card.clicked.connect(self.on_card_clicked)
            card.double_clicked.connect(self.on_card_double_clicked)
            self.flow_widget.add_item(card)
            self.image_cards.append(card)

        # Restore selection if still exists
        if self.selected_image and self.selected_image in all_images:
            for card in self.image_cards:
                if card.image_path == self.selected_image:
                    card.set_selected(True)
                    break
        else:
            self.selected_image = None

        self._update_selection_buttons()

    def on_search_changed(self, text):
        self.search_timer.start(1000)

    def on_card_clicked(self, image_path):
        # Toggle selection
        if self.selected_image == image_path:
            self.selected_image = None
        else:
            self.selected_image = image_path

        for card in self.image_cards:
            card.set_selected(card.image_path == self.selected_image)

        self._update_selection_buttons()

    def on_card_double_clicked(self, image_path):
        """Double-click on an image card opens the markup editor."""
        self.selected_image = image_path
        for card in self.image_cards:
            card.set_selected(card.image_path == self.selected_image)
        self._update_selection_buttons()
        self.open_markup()

    def _update_selection_buttons(self):
        has_sel = self.selected_image is not None
        self.markup_btn.setVisible(has_sel)
        self.delete_btn.setVisible(has_sel)

    def take_screenshot(self):
        """Capture a frame and save it to ok_templates."""
        try:
            if og.device_manager.capture_method is None:
                from ok.gui.util.Alert import alert_error
                alert_error(self.tr("No capture method available. Please start capture first."))
                return

            frame = og.device_manager.capture_method.get_frame()
            if frame is None:
                from ok.gui.util.Alert import alert_error
                alert_error(self.tr("Failed to capture frame."))
                return

            if processor := og.config.get('screenshot_processor'):
                frame = processor(frame.copy())

            folder = ensure_template_folder()
            name = get_next_image_name(folder)
            file_path = os.path.join(folder, f"{name}.png")
            cv2.imwrite(file_path, frame)

            # Add image to COCO data
            self._add_image_to_coco(file_path)

            from ok.gui.util.Alert import alert_info
            alert_info(self.tr("Screenshot saved: {}").format(os.path.basename(file_path)))

            self.refresh_grid()
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            from ok.gui.util.Alert import alert_error
            alert_error(self.tr("Screenshot failed: {e}").format(e=e))

    def _add_image_to_coco(self, image_path):
        """Add an image entry to COCO data if not already present."""
        filename = os.path.basename(image_path)
        for img in self.coco_data.get('images', []):
            if img['file_name'] == filename:
                return  # Already exists

        # Read image dimensions
        img = cv2.imread(image_path)
        if img is not None:
            h, w = img.shape[:2]
        else:
            h, w = 0, 0

        # Find max id
        max_id = 0
        for im in self.coco_data.get('images', []):
            if im['id'] > max_id:
                max_id = im['id']

        self.coco_data['images'].append({
            'id': max_id + 1,
            'file_name': filename,
            'width': w,
            'height': h
        })
        save_coco(self.coco_data)

    def delete_image(self):
        if not self.selected_image:
            return

        w = MessageBox(self.tr('Confirm Delete'),
                       self.tr("Are you sure you want to delete '{}'?").format(
                           os.path.basename(self.selected_image)),
                       self.window())
        if w.exec():
            try:
                filename = os.path.basename(self.selected_image)

                # Remove from filesystem
                if os.path.exists(self.selected_image):
                    os.remove(self.selected_image)

                # Remove from COCO data
                image_id = None
                img_to_remove = None
                for img in self.coco_data.get('images', []):
                    if img['file_name'] == filename:
                        img_to_remove = img
                        image_id = img['id']
                        break
                if img_to_remove:
                    self.coco_data['images'].remove(img_to_remove)
                if image_id is not None:
                    self.coco_data['annotations'] = [
                        ann for ann in self.coco_data.get('annotations', [])
                        if ann['image_id'] != image_id
                    ]

                # Clean up orphaned categories
                used_cat_ids = set(ann['category_id'] for ann in self.coco_data.get('annotations', []))
                self.coco_data['categories'] = [
                    cat for cat in self.coco_data.get('categories', [])
                    if cat['id'] in used_cat_ids
                ]

                save_coco(self.coco_data)

                self.selected_image = None
                self.refresh_grid()

                from ok.gui.util.app import show_info_bar
                show_info_bar(self.window(), self.tr("Image deleted."), title=self.tr("Success"))
            except Exception as e:
                logger.error(f"Delete error: {e}")
                from ok.gui.util.Alert import alert_error
                alert_error(self.tr("Delete failed: {e}").format(e=e))

    def _normalize_label_enum_relative_path(self, relative_path):
        path = (relative_path or "").strip().replace('\\', '/')
        if not path or os.path.isabs(path):
            return None

        normalized = os.path.normpath(path).replace('\\', '/')
        if normalized in ('', '.') or normalized == '..' or normalized.startswith('../'):
            return None

        if normalized.lower().endswith('.py'):
            normalized = normalized[:-3]

        module_path = normalized.replace('/', '.').strip('.')
        if not module_path:
            return None

        parts = module_path.split('.')
        if any(not part or not part.isidentifier() for part in parts):
            return None

        return module_path

    def save_compressed(self):
        """Show a dialog with radio buttons for save destination."""
        from ok.feature.FeatureSet import compress_copy_coco
        from PySide6.QtWidgets import QButtonGroup
        from qfluentwidgets import MessageBoxBase, SubtitleLabel, RadioButton, CheckBox, LineEdit
        coco_json_path = get_coco_path()
        image_folder = ensure_template_folder()

        if not os.path.exists(coco_json_path):
            from ok.gui.util.Alert import alert_error
            alert_error(self.tr("No annotations to save."))
            return

        tasks_target = os.path.abspath(os.path.join('ok_tasks', 'assets'))
        dev_target = os.path.abspath('assets')

        dlg = MessageBoxBase(self.window())
        dlg.viewLayout.addWidget(SubtitleLabel(self.tr('Save To'), dlg))

        debug = og.app.debug
        radio_tasks = RadioButton(self.tr('ok_tasks/assets (custom scripts)'), dlg)
        radio_dev = None
        if debug:
            radio_dev = RadioButton(self.tr('assets (standalone app)'), dlg)

        group = QButtonGroup(dlg)
        group.addButton(radio_tasks)
        if radio_dev:
            group.addButton(radio_dev)

        # Default selection based on environment
        if debug:
            radio_dev.setChecked(True)
        else:
            radio_tasks.setChecked(True)

        dlg.viewLayout.addWidget(radio_tasks)
        if radio_dev:
            dlg.viewLayout.addWidget(radio_dev)

        saved_generate_label_enum = bool(self.template_tab_config.get('generate_label_enum', False))
        saved_enum_relative_path = str(self.template_tab_config.get('label_enum_relative_path', '') or '').strip()

        generate_label_enum_checkbox = CheckBox(self.tr('Generate label enum file'), dlg)
        generate_label_enum_checkbox.setChecked(saved_generate_label_enum)
        dlg.viewLayout.addWidget(generate_label_enum_checkbox)

        enum_relative_path_input = LineEdit(dlg)
        enum_relative_path_input.setPlaceholderText(self.tr('Relative path, e.g. ok_tasks/LabelEnum.py'))
        enum_relative_path_input.setText(saved_enum_relative_path)
        enum_relative_path_input.setEnabled(saved_generate_label_enum)
        dlg.viewLayout.addWidget(enum_relative_path_input)

        enum_path_hint = BodyLabel(self.tr('Path is relative to the workspace root.'))
        enum_path_hint.setStyleSheet("color: gray;")
        enum_path_hint.setVisible(saved_generate_label_enum)
        dlg.viewLayout.addWidget(enum_path_hint)

        def on_generate_label_toggled(checked):
            enum_relative_path_input.setEnabled(checked)
            enum_path_hint.setVisible(checked)
            if checked:
                enum_relative_path_input.setFocus()

        generate_label_enum_checkbox.toggled.connect(on_generate_label_toggled)

        dlg.yesButton.setText(self.tr('OK'))
        dlg.cancelButton.setText(self.tr('Cancel'))
        dlg.widget.setMinimumWidth(360)

        if not dlg.exec():
            return

        target_folder = tasks_target if radio_tasks.isChecked() else dev_target
        enum_relative_path_text = enum_relative_path_input.text().strip().replace('\\', '/')
        self.template_tab_config['generate_label_enum'] = generate_label_enum_checkbox.isChecked()
        self.template_tab_config['label_enum_relative_path'] = enum_relative_path_text

        generate_label_enmu = None
        if generate_label_enum_checkbox.isChecked():
            generate_label_enmu = self._normalize_label_enum_relative_path(enum_relative_path_text)
            if not generate_label_enmu:
                from ok.gui.util.Alert import alert_error
                alert_error(self.tr("Invalid relative path. Example: ok_tasks/LabelEnum.py"))
                return

        try:
            compress_copy_coco(coco_json_path, target_folder, image_folder,
                               generate_label_enmu=generate_label_enmu)

            # Reload feature set data safely (coco_json may have been cleared)
            try:
                if og.executor.feature_set is not None:
                    og.executor.feature_set.process_data()
            except Exception as e:
                logger.warning(f"Could not reload feature set after save: {e}")

            from ok.gui.util.Alert import alert_info
            alert_info(self.tr("Save completed successfully to: {}").format(target_folder))
        except Exception as e:
            logger.error(f"Save compressed error: {e}", e)
            from ok.gui.util.Alert import alert_error
            alert_error(self.tr("Save failed: {e}").format(e=e))

    def open_markup(self):
        if not self.selected_image:
            return

        # Only one markup window at a time
        if self.markup_window is not None and self.markup_window.isVisible():
            self.markup_window.activateWindow()
            self.markup_window.raise_()
            return

        from ok.gui.tasks.MarkUpWindow import MarkUpWindow
        all_images = get_image_files()
        query = self.search_box.text().strip().lower()
        if query:
            filtered = []
            for img_path in all_images:
                name = os.path.splitext(os.path.basename(img_path))[0].lower()
                cats = get_categories_for_image(self.coco_data, img_path)
                cat_str = ' '.join(cats).lower()
                if query in name or query in cat_str:
                    filtered.append(img_path)
            all_images = filtered

        self.markup_window = MarkUpWindow(self.selected_image, all_images)
        self.markup_window.closed.connect(self.on_markup_closed)
        self.markup_window.show()

    def on_markup_closed(self):
        self.markup_window = None

