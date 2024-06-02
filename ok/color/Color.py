import cv2

black_color = {
    'r': (0, 0),  # Red range
    'g': (0, 0),  # Green range
    'b': (0, 0)  # Blue range
}

white_color = {
    'r': (255, 255),  # Red range
    'g': (255, 255),  # Green range
    'b': (255, 255)  # Blue range
}


def calculate_color_percentage(image, color_ranges, box=None):
    # Check if the ROI is within the image bounds
    if box is not None:
        if (box.x >= 0 and box.y >= 0 and
            box.x + box.width <= image.shape[1] and  # image.shape[1] is the width of the image
            box.y + box.height <= image.shape[
                0]) and box.width > 0 and box.height > 0:  # image.shape[0] is the height of the image

            # Extract the region of interest (ROI) using slicing

            image = image[box.y:box.y + box.height, box.x:box.x + box.width, :3]
        else:
            # Return some error value or raise an exception
            # For example, return 0 or None
            return 0  # or None, or raise an exception
    else:
        image = image[:, :, :3]
    # Create a mask for the pixels within the desired color range
    mask = cv2.inRange(image,
                       (color_ranges['b'][0], color_ranges['g'][0], color_ranges['r'][0]),
                       (color_ranges['b'][1], color_ranges['g'][1], color_ranges['r'][1]))

    # Calculate the percentage of pixels within the color range
    target_pixels = cv2.countNonZero(mask)
    total_pixels = image.size / 3  # Divide by 3 for an RGB image
    percentage = target_pixels / total_pixels
    return percentage
