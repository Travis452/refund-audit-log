import cv2
import pytesseract
import re
import logging
import os
import numpy as np
import signal
from datetime import datetime

# Set up a timeout handler to prevent OCR from hanging
class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("OCR processing timed out - image might be too complex")

# Set the default timeout for OCR operations to 10 seconds to avoid Gunicorn worker timeout
# Gunicorn's default worker timeout is 30 seconds, so we need to finish faster
OCR_TIMEOUT_SECONDS = 10

# This function is now integrated into process_image

def process_quick(image_path):
    """Fast version of OCR that extracts just basic numbers without extensive preprocessing."""
    try:
        logging.info(f"Using quick processing for image: {image_path}")
        
        # Check if the file exists
        if not os.path.exists(image_path):
            return "Error: Image file not found"
            
        # Use direct OCR with minimal preprocessing
        import cv2
        
        # Read image
        img = cv2.imread(image_path, 0)  # Grayscale
        if img is None:
            return "Error: Unable to read image file"
            
        # Simple resize if image is too large
        h, w = img.shape
        if max(h, w) > 1000:
            ratio = 1000 / max(h, w)
            img = cv2.resize(img, (int(w * ratio), int(h * ratio)))
            
        # Simple binary threshold
        _, binary = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY)
        
        # Run OCR with digit-focused configuration
        import pytesseract
        digit_config = '--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789'
        result = pytesseract.image_to_string(binary, config=digit_config)
        
        if result:
            return result
        else:
            return "Error: Quick OCR returned empty result"
            
    except Exception as e:
        logging.error(f"Error in quick process: {str(e)}")
        return f"Error: Quick processing failed: {str(e)}"

def process_image(image_path):
    """Process the image with OCR to extract text, with extra focus on item numbers."""
    try:
        # Configure logging
        logging.basicConfig(level=logging.DEBUG)
        logging.info(f"Processing image: {image_path}")
        
        # Check if the image file exists
        if not os.path.exists(image_path):
            logging.error(f"Image file not found: {image_path}")
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        logging.info(f"Image file exists, size: {os.path.getsize(image_path)} bytes")
        
        # Define item numbers to find in the image - we'll try to detect them through OCR
        # but need to implement a better processing approach specifically for numbers
        ocr_results = []
        
        # Set up timeout to prevent hanging
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(OCR_TIMEOUT_SECONDS)
        logging.info(f"Setting OCR timeout to {OCR_TIMEOUT_SECONDS} seconds")
        
        try:
            # Read the image
            img = cv2.imread(image_path)
            if img is None:
                logging.error("Failed to read image - it may be corrupted or in an unsupported format")
                # Return a fallback message to avoid crashing
                return "Error: Could not process image. It may be corrupted or in an unsupported format."
            
            # First, try a faster approach that optimizes specifically for item numbers
            # Resize the image to make processing faster
            image_h, image_w = img.shape[:2]
            logging.info(f"Original image dimensions: {image_w}x{image_h}")
            
            # Only resize if the image is very large
            max_dim = 1800
            scale_factor = 1.0
            if max(image_h, image_w) > max_dim:
                scale_factor = max_dim / max(image_h, image_w)
                new_w = int(image_w * scale_factor)
                new_h = int(image_h * scale_factor)
                img = cv2.resize(img, (new_w, new_h))
                logging.info(f"Resized image to {new_w}x{new_h} for faster processing")
            
            # Create a working copy
            original_img = img.copy()
            
            # Convert to grayscale
            gray = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY)
            
            # Enhanced preprocessing techniques specifically for number recognition on receipts
            
            # Apply noise reduction 
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            
            # Sharpening to enhance digit edges
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(gray, -1, kernel)
            
            # Technique 1: Basic thresholding for clear text
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            
            # Technique 2: Adaptive thresholding for receipt-like documents
            adaptive = cv2.adaptiveThreshold(
                denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
            
            # Technique 3: Otsu's thresholding for better separation
            _, otsu = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Technique 4: Contrast enhancement specifically for receipts
            # Create a CLAHE object (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            _, enhanced_binary = cv2.threshold(enhanced, 150, 255, cv2.THRESH_BINARY)
            
            # Use only the most effective preprocessing techniques to save time
            # Binary and adaptive typically work best for receipts
            preprocessed_imgs = [binary, adaptive]
            
            # Skip saving debug images to improve performance
            logging.info(f"Using {len(preprocessed_imgs)} preprocessed images for OCR")
            
            # OCR configurations optimized for digit recognition on receipts
            # PSM modes:
            # 3 = Fully automatic page segmentation, but no OSD (default)
            # 4 = Assume a single column of text of variable sizes
            # 6 = Assume a single uniform block of text
            # 7 = Treat the image as a single text line
            # 8 = Treat the image as a single word
            # 10 = Treat the image as a single character
            # 11 = Sparse text. Find as much text as possible in no particular order
            
            # Use only the most effective configurations to save processing time
            # Just two configurations that work best for receipt digit extraction
            digit_configs = [
                '--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789',   # Single block mode - usually best for receipt item numbers
            ]
            
            # Just one standard config for general text
            standard_configs = [
                '--psm 3 --oem 3',  # Default for general OCR
            ]
            
            # For each preprocessed image, run OCR with multiple configurations
            for i, p_img in enumerate(preprocessed_imgs):
                logging.info(f"Running OCR on preprocessed image {i}")
                
                # Try all standard OCR configs for general text extraction
                for config_idx, config in enumerate(standard_configs):
                    try:
                        ocr_text = pytesseract.image_to_string(p_img, config=config)
                        ocr_results.append(ocr_text)
                        logging.info(f"Image {i+1}, standard config {config_idx+1} extracted {len(ocr_text)} characters")
                    except Exception as ocr_error:
                        logging.error(f"Standard OCR failed on image {i+1}, config {config_idx+1}: {str(ocr_error)}")
                
                # Try all digit-specific OCR configs for number detection
                for config_idx, config in enumerate(digit_configs):
                    try:
                        digit_text = pytesseract.image_to_string(p_img, config=config)
                        ocr_results.append(digit_text)
                        logging.info(f"Image {i+1}, digit config {config_idx+1} extracted {len(digit_text)} characters")
                    except Exception as ocr_error:
                        logging.error(f"Digit OCR failed on image {i+1}, config {config_idx+1}: {str(ocr_error)}")
            
            # Only process the middle section which typically contains the important data
            # This is much faster than processing the entire image in segments
            try:
                # Create a single segment from the middle third of the image - often where item numbers are located
                img_height, img_width = gray.shape[:2]
                
                # Extract just the middle horizontal section
                middle_y = img_height // 3
                segment = gray[middle_y:middle_y*2, :]
                
                if segment.size > 1000:  # Only process if segment is large enough
                    logging.info(f"Processing middle segment of image from y={middle_y} to y={middle_y*2}")
                    
                    # Use the digit-specific config since we're primarily looking for item numbers
                    segment_text = pytesseract.image_to_string(segment, config=digit_configs[0])
                    ocr_results.append(segment_text)
                    logging.info(f"Middle segment extracted {len(segment_text)} characters")
            except Exception as segment_error:
                logging.error(f"Segment processing failed: {str(segment_error)}")
                
            # Try one more pass on just the center part of denoised grayscale image
            try:
                # Focus on the center region where item numbers typically appear
                h, w = denoised.shape[:2]
                center_region = denoised[h//3:2*h//3, w//4:3*w//4]
                
                logging.info("Running OCR on center region of denoised image")
                center_text = pytesseract.image_to_string(center_region, config='--psm 6 --oem 3')
                ocr_results.append(center_text)
                logging.info(f"Center region OCR extracted {len(center_text)} characters")
            except Exception as e:
                logging.error(f"Center region OCR failed: {str(e)}")
                
            # Combine all OCR results
            combined_text = "\n".join(ocr_results)
            logging.info(f"Combined OCR text length: {len(combined_text)}")
            
            # Cancel the alarm since OCR completed
            signal.alarm(0)
            
            # Return the combined OCR results for further processing
            return combined_text
            
        except TimeoutError as timeout_error:
            # Caught a timeout - cancel the alarm and provide a specific error message
            signal.alarm(0)
            logging.error(f"OCR processing timed out after {OCR_TIMEOUT_SECONDS} seconds: {str(timeout_error)}")
            return f"Error: OCR processing timed out after {OCR_TIMEOUT_SECONDS} seconds. The image may be too complex or large to process."
            
        except Exception as inner_e:
            # Cancel the alarm for other exceptions too
            signal.alarm(0)
            logging.error(f"Error during image processing or OCR: {str(inner_e)}")
            
            # Fall back to basic OCR if everything else fails
            try:
                logging.info("Attempting direct OCR without preprocessing as final fallback...")
                # Set a new timeout for the fallback attempt
                signal.alarm(15)  # 15 second timeout for the fallback
                
                # Try reading just a portion of the image as one last resort
                logging.info("Reading just the center portion of the image as last resort")
                img = cv2.imread(image_path)
                if img is not None:
                    h, w = img.shape[:2]
                    # Extract the center region (1/3 of the image)
                    center_img = img[h//3:2*h//3, w//3:2*w//3]
                    # Try with the best digit recognition config
                    best_digit_config = '--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789'
                    extracted_text = pytesseract.image_to_string(center_img, config=best_digit_config)
                    # Cancel timeout
                    signal.alarm(0)
                    return extracted_text
                else:
                    signal.alarm(0)
                    return "Error: Could not read image file as fallback."
            except Exception as fallback_error:
                # Cancel timeout
                signal.alarm(0)
                logging.error(f"Fallback OCR also failed: {str(fallback_error)}")
                # If that fails too, return an error message
                return "Error: Failed to process image after multiple attempts."
            
    except Exception as e:
        logging.error(f"Error in process_image: {str(e)}")
        # Return a message instead of raising to avoid crashing
        return f"Error processing image: {str(e)}"

def extract_data_from_text(text):
    """Extract structured data from OCR text."""
    logging.info("Starting data extraction from OCR text")
    logging.debug(f"Text to process: {text[:500]}...")
    
    items = []
    
    # Split text into lines
    lines = text.strip().split('\n')
    logging.info(f"Split text into {len(lines)} lines")
    
    # Extract the receipt date (typically near the top)
    report_date = None
    date_pattern = r'Date:?\s*(\d{2}/\d{2}/\d{2,4})'
    for i in range(min(10, len(lines))):
        date_match = re.search(date_pattern, lines[i], re.IGNORECASE)
        if date_match:
            report_date = date_match.group(1)
            logging.info(f"Found report date: {report_date}")
            break
    
    # If no date found with the specific pattern, try a more generic one
    if not report_date:
        for i in range(min(10, len(lines))):
            date_match = re.search(r'(\d{2}/\d{2}/\d{2,4})', lines[i])
            if date_match:
                report_date = date_match.group(1)
                logging.info(f"Found report date with generic pattern: {report_date}")
                break
    
    logging.info("Looking for item data in text")
    
    # Patterns specifically designed for your receipt format - updated based on image.jpg
    member_line_pattern = r'Member#:\s*(\d+).*?(\d+\.\d{2})'
    operator_line_pattern = r'Operator ID:\s*(\d+).*?(\d+\.\d{2})'
    
    # Track which item numbers we've already processed to avoid duplicates
    processed_items = set()
    
    # First pass: Look for Member# and Operator ID lines which contain item numbers and prices
    for i, line in enumerate(lines):
        # Search for Member# pattern
        member_match = re.search(member_line_pattern, line)
        if member_match:
            item_number = member_match.group(1)
            price = member_match.group(2)
            
            # Extract description - it's usually between the item number and price
            description = ""
            desc_match = re.search(r'Member#:\s*\d+\s*(.*?)\s*\d+\.\d{2}', line)
            if desc_match:
                description = desc_match.group(1).strip()
            
            # Try to find the date for this item
            item_date = report_date
            date_in_line = re.search(r'Date:?\s*(\d{2}/\d{2}/\d{2,4})', line)
            if date_in_line:
                item_date = date_in_line.group(1)
            
            # Look for time information
            time_match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
            time_value = time_match.group(1) if time_match else ''
            
            # Only add if we haven't seen this item number before
            if item_number not in processed_items:
                processed_items.add(item_number)
                
                item_data = {
                    'item_number': item_number,
                    'price': price,
                    'date': item_date or '',
                    'time': time_value,
                    'description': description or f"Item {item_number}"
                }
                items.append(item_data)
                logging.info(f"Found item with Member# pattern: {item_data}")
        
        # Search for Operator ID pattern
        operator_match = re.search(operator_line_pattern, line)
        if operator_match:
            item_number = operator_match.group(1)
            price = operator_match.group(2)
            
            # Extract description
            description = ""
            desc_match = re.search(r'Operator ID:\s*\d+\s*(.*?)\s*\d+\.\d{2}', line)
            if desc_match:
                description = desc_match.group(1).strip()
            
            # Try to find the date for this item
            item_date = report_date
            date_in_line = re.search(r'Date:?\s*(\d{2}/\d{2}/\d{2,4})', line)
            if date_in_line:
                item_date = date_in_line.group(1)
            
            # Look for time information
            time_match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
            time_value = time_match.group(1) if time_match else ''
            
            # Only add if we haven't seen this item number before
            if item_number not in processed_items:
                processed_items.add(item_number)
                
                item_data = {
                    'item_number': item_number,
                    'price': price,
                    'date': item_date or '',
                    'time': time_value,
                    'description': description or f"Item {item_number}"
                }
                items.append(item_data)
                logging.info(f"Found item with Operator ID pattern: {item_data}")
    
    # If we found items using the specific patterns, return them
    if items:
        logging.info(f"Found {len(items)} items using Member#/Operator ID patterns")
        
        # Extract period from date if available
        for item in items:
            if 'date' in item and item['date'] and '/' in item['date']:
                try:
                    month = item['date'].split('/')[0]
                    if month.isdigit():
                        item['period'] = f"P{month.zfill(2)}"
                except Exception:
                    pass
        
        return items
    
    # Second pass: If the specific patterns didn't work, fall back to more generic detection
    logging.info("No items found with specific patterns, trying more generic detection")
    
    # Look for lines that contain both an 8-digit number and a price
    item_pattern = r'(\d{6,8})'
    price_pattern = r'(\d+\.\d{2})'
    time_pattern = r'(\d{2}:\d{2}:\d{2})'
    
    for line in lines:
        # Skip short lines that likely don't contain full item info
        if len(line) < 20:
            continue
        
        item_matches = re.findall(item_pattern, line)
        price_matches = re.findall(price_pattern, line)
        
        if item_matches and price_matches:
            for item_number in item_matches:
                # Skip if we've already processed this item
                if item_number in processed_items:
                    continue
                
                processed_items.add(item_number)
                
                # Find the closest price to this item number in the line
                item_pos = line.find(item_number)
                closest_price = None
                closest_dist = float('inf')
                
                for price in price_matches:
                    price_pos = line.find(price)
                    dist = abs(price_pos - item_pos)
                    if dist < closest_dist:
                        closest_price = price
                        closest_dist = dist
                
                # Extract description and time if available
                description = ""
                time_value = ""
                
                # Try to find time in the line
                time_match = re.search(time_pattern, line)
                if time_match:
                    time_value = time_match.group(1)
                
                item_data = {
                    'item_number': item_number,
                    'price': closest_price,
                    'date': report_date or '',
                    'time': time_value,
                    'description': description or f"Item {item_number}"
                }
                items.append(item_data)
                logging.info(f"Found item with generic pattern: {item_data}")
    
    # If we still have no items, try a more aggressive approach to extract all possible items
    if not items:
        logging.info("No items found with per-line patterns, extracting all possible items")
        
        # Get all item numbers and prices from the entire text
        all_items = re.findall(item_pattern, text)
        all_prices = re.findall(price_pattern, text)
        all_times = re.findall(time_pattern, text)
        
        logging.info(f"Found {len(all_items)} potential item numbers and {len(all_prices)} potential prices")
        
        # Match items with prices based on proximity in the text
        count = min(len(all_items), len(all_prices), 50)  # Process up to 50 items
        
        for i in range(count):
            if i >= len(all_items):
                break
                
            item_number = all_items[i]
            
            # Skip if we've already processed this item
            if item_number in processed_items:
                continue
                
            processed_items.add(item_number)
            
            # Get the price - either at the same index or find closest
            price = all_prices[i] if i < len(all_prices) else all_prices[0]
            
            # Get time if available
            time_value = all_times[i] if i < len(all_times) else ""
            
            item_data = {
                'item_number': item_number,
                'price': price,
                'date': report_date or '',
                'time': time_value,
                'description': f"Item {item_number}"
            }
            items.append(item_data)
    
    # If we still have no items, create at least one default item
    if not items:
        logging.warning("No items could be extracted from text, creating default item")
        items.append({
            'item_number': '12345678',
            'price': '0.00',
            'date': datetime.now().strftime('%m/%d/%y'),
            'time': datetime.now().strftime('%H:%M:%S'),
            'description': 'No data extracted from image'
        })
    
    logging.info(f"Extracted {len(items)} items from text")
    for i, item in enumerate(items):
        logging.debug(f"Item {i+1}: {item}")
    
    # Extract period from date if available
    for item in items:
        if 'date' in item and item['date'] and '/' in item['date']:
            try:
                month = item['date'].split('/')[0]
                if month.isdigit():
                    item['period'] = f"P{month.zfill(2)}"
            except Exception:
                pass
    
    return items
