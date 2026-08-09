# Introduction to computer-vision game automation

[Documentation](index.md) · [Quick start](quick_start.md) · [API reference](api_reference.md) · [简体中文](../intro_to_automation/README.md)

This guide introduces the basic ideas and tools behind game automation with computer vision. No prior image-processing experience is required.

## 1. How a computer “plays” a game

Most visual automation follows the same loop:

1. **Observe:** capture the game window or device screen.
2. **Decide:** analyze pixels, text, or detected objects to determine the current state.
3. **Act:** click, press a key, swipe, or wait for the next state.

The loop repeats until the task succeeds, fails, or is stopped.

### Capture

A screenshot is a matrix of pixels. A 1920×1080 image contains more than two million pixels, usually represented as blue, green, and red channel values. The capture backend determines whether automation can continue while a window is covered or minimized.

### Decision making

A task turns visual observations into state. Examples include:

- a button template is visible, so it can be clicked;
- OCR reads “Battle Complete,” so the result screen is ready;
- a health-bar region contains less than a threshold of green pixels, so healing is required;
- an object detector finds an enemy, so the cursor should move toward its bounding box.

### Input

After choosing an action, the framework sends mouse, keyboard, touch, or ADB input. Some actions happen immediately; others wait for a visual condition before continuing.

## 2. Image-analysis approaches

### Traditional computer vision

Traditional OpenCV methods are lightweight, deterministic, and often the best first choice for game interfaces.

**Template matching** searches the screenshot for a small reference image. It works well for stable buttons, icons, and UI elements. ok-script adds position hints and resolution scaling through COCO annotations.

**Color matching** measures or searches for pixels in a color range. Typical uses include health bars, highlighted controls, and status indicators.

**Geometry and contours** identify edges, shapes, and filled regions. They can measure progress bars or locate objects with a distinctive silhouette.

### Neural-network inference

Neural models are useful when appearance varies too much for a fixed template.

- **OCR** extracts text such as player names, counters, or quest descriptions.
- **Object detection** locates multiple objects and returns bounding boxes. It is more tolerant of scale, rotation, and partial occlusion than template matching.
- **Segmentation** returns detailed object regions and is useful for navigation or irregular shapes.
- **Classification** selects one state from a set, such as menu, combat, or map.
- **Vision-language models** can interpret broader visual scenes, but they are usually slower and less deterministic than purpose-built recognition.

Start with the simplest technique that reliably distinguishes the states your task needs.

## 3. Why Python

Python is a practical choice for visual automation because it combines readable task code with a mature ecosystem:

- [OpenCV](https://opencv.org/) for image processing and template matching
- [NumPy](https://numpy.org/) for efficient pixel and array operations
- OCR libraries for reading interface text
- [PyTorch](https://pytorch.org/) and [ONNX Runtime](https://onnxruntime.ai/) for model inference
- [PySide6](https://doc.qt.io/qtforpython-6/) for desktop interfaces
- pytest or unittest for repeatable task tests

ok-script integrates these concerns so application projects can focus on task logic.

## 4. Development tools

- **IDE:** [PyCharm](https://www.jetbrains.com/pycharm/download/) or [Visual Studio Code](https://code.visualstudio.com/download)
- **Version control:** [Git](https://git-scm.com/) and [GitHub](https://github.com/)
- **CI/CD:** GitHub Actions for tests, builds, and releases
- **Annotation:** any tool that exports compatible COCO data; the advanced guide describes the workflow

## 5. A practical first task

A useful first automation should have a small number of distinct states:

1. Capture a screenshot of a stable screen.
2. Annotate one button as a template.
3. Use `find_one` or `wait_feature` to locate it.
4. Click the returned `Box`.
5. Assert the next screen appears.

This exercise introduces the full observe–decide–act loop without requiring a neural model.

Continue with the [quick-start guide](quick_start.md) to create a runnable project.
