import cv2
import numpy as np

from ok.feature.Box import Box

black_color = {
    'r': (0, 0),
    'g': (0, 0),
    'b': (0, 0)
}

white_color = {
    'r': (255, 255),
    'g': (255, 255),
    'b': (255, 255)
}


def is_close_to_pure_color(image, max_colors=5000, percent=0.97):
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    color_counts = {}
    total_pixels = image.shape[0] * image.shape[1]

    for row in image:
        for pixel in row:
            color = tuple(pixel)
            color_counts[color] = color_counts.get(color, 0) + 1
            if len(color_counts) > max_colors:
                return False

    dominant_color = max(color_counts, key=color_counts.get)
    dominant_count = color_counts[dominant_color]
    percentage = (dominant_count / total_pixels)
    return percentage > percent


def get_mask_in_color_range(image, color_range):
    lower_bound, upper_bound = color_range_to_bound(color_range)
    mask = cv2.inRange(image, lower_bound, upper_bound)
    pixel_count = np.count_nonzero(mask)

    return mask, pixel_count


def get_connected_area_by_color(image, color_range, connectivity=4, gray_range=0):
    lower_bound, upper_bound = color_range_to_bound(color_range)
    mask = cv2.inRange(image, lower_bound, upper_bound)
    if gray_range > 0:
        diff_rg = np.abs(image[:, :, 0] - image[:, :, 1])
        diff_gb = np.abs(image[:, :, 1] - image[:, :, 2])
        diff_br = np.abs(image[:, :, 2] - image[:, :, 0])
        gray_mask = (diff_rg <= 10) & (diff_gb <= 10) & (diff_br <= 10)
        gray_mask = gray_mask.astype(np.uint8) * 255
        mask = mask & gray_mask

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=connectivity)
    return num_labels, stats, labels


def color_range_to_bound(color_range):
    lower_bound = np.array([color_range['b'][0], color_range['g'][0], color_range['r'][0]], dtype="uint8")
    upper_bound = np.array([color_range['b'][1], color_range['g'][1], color_range['r'][1]], dtype="uint8")
    return lower_bound, upper_bound


def calculate_colorfulness(image, box=None):
    if box is not None:
        image = image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
    B, G, R = cv2.split(image.astype("float"))
    rg = np.absolute(R - G)
    yb = np.absolute(0.5 * (R + G) - B)
    rbMean, rbStd = np.mean(rg), np.std(rg)
    ybMean, ybStd = np.mean(yb), np.std(yb)
    stdRoot = np.sqrt((rbStd ** 2) + (ybStd ** 2))
    meanRoot = np.sqrt((rbMean ** 2) + (ybMean ** 2))
    colorfulness = stdRoot + (0.3 * meanRoot)

    return colorfulness / 100


def get_saturation(image, box=None):
    if image is None:
        raise ValueError("Image not found or path is incorrect")

    if box is not None:
        if (box.x >= 0 and box.y >= 0 and
                box.x + box.width <= image.shape[1] and box.y + box.height <= image.shape[0] and
                box.width > 0 and box.height > 0):
            image = image[box.y:box.y + box.height, box.x:box.x + box.width, :3]

    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation_channel = hsv_image[:, :, 1]
    mean_saturation = saturation_channel.mean() / 255

    return mean_saturation


def find_color_rectangles(image, color_range, min_width, min_height,
                          max_width=-1, max_height=-1, threshold=0.95, box=None):
    if image is None:
        raise ValueError("Image not found or path is incorrect")

    if box is not None:
        image = image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
        x_offset = box.x
        y_offset = box.y
    else:
        x_offset = 0
        y_offset = 0

    lower_bound, upper_bound = color_range_to_bound(color_range)
    mask = cv2.inRange(image, lower_bound, upper_bound)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    results = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= min_width and h >= min_height and (max_height == -1 or h <= max_height) and (
                max_width == -1 or w <= max_width):
            roi_mask = mask[y:y + h, x:x + w]
            total_pixels = roi_mask.size
            matching_pixels = np.sum(roi_mask == 255)
            percent = (matching_pixels / total_pixels)
            if percent >= threshold:
                results.append(Box(x + x_offset, y + y_offset, w, h, confidence=percent))

    return results


def mask_white(image, lower_white=255):
    # Check if the image is grayscale
    if len(image.shape) == 2 or image.shape[2] == 1:
        # Image is grayscale
        lower_white = np.array([lower_white])
        upper_white = np.array([255])
    else:
        # Image is in color
        lower_white = np.array([lower_white, lower_white, lower_white])
        upper_white = np.array([255, 255, 255])

    # Create a mask for the white color
    return cv2.inRange(image, lower_white, upper_white)


def is_pure_black(frame):
    for channel in cv2.split(frame):
        if cv2.countNonZero(channel) > 0:
            return False
    return True


def calculate_color_percentage(image, color_ranges, box=None):
    if box is not None:
        if (box.x >= 0 and box.y >= 0 and
                box.x + box.width <= image.shape[1] and box.y + box.height <= image.shape[0] and
                box.width > 0 and box.height > 0):
            image = image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
        else:
            return 0
    else:
        image = image[:, :, :3]

    mask = cv2.inRange(image, (color_ranges['b'][0], color_ranges['g'][0], color_ranges['r'][0]),
                       (color_ranges['b'][1], color_ranges['g'][1], color_ranges['r'][1]))
    target_pixels = cv2.countNonZero(mask)
    total_pixels = image.size / 3
    percentage = target_pixels / total_pixels
    return percentage


def create_non_black_mask(image):
    if image is None:
        raise ValueError("Input image cannot be None")
    if image.ndim == 2:
        _, mask = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY)
    elif image.ndim == 3 and image.shape[2] in [3, 4]:
        lower_black = np.array([0, 0, 0], dtype="uint8")
        upper_black = np.array([0, 0, 0], dtype="uint8")
        mask_black = cv2.inRange(image[:, :, :3], lower_black, upper_black)
        mask = cv2.bitwise_not(mask_black)
    else:
        raise ValueError("Input image must be Grayscale (2D) or BGR/BGRA (3D)")
    return mask
