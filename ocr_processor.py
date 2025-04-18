import cv2
import pytesseract
import re
import logging
import os
import numpy as np
import signal
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter
import time

# Set up a timeout handler to prevent OCR from hanging
class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("OCR processing timed out - image might be too complex")

# Set the default timeout for OCR operations to 5 seconds to avoid Gunicorn worker timeout
# Gunicorn's default worker timeout is 30 seconds, so we need to finish much faster
OCR_TIMEOUT_SECONDS = 5

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
    """Ultra-simplified image processing with OCR focusing only on finding item numbers."""
    try:
        logging.info(f"Starting simplified image processing: {image_path}")
        
        # Check if the file exists
        if not os.path.exists(image_path):
            return "Error: Image file not found"
        
        # Set ultra-short timeout to avoid worker hanging
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(OCR_TIMEOUT_SECONDS)
        logging.info(f"Set timeout to {OCR_TIMEOUT_SECONDS} seconds")
        
        # Process the image
        try:
            # Use PIL for faster processing
            pil_img = Image.open(image_path)
            
            # Convert to grayscale
            pil_img = pil_img.convert('L')
            
            # Resize if too large
            if max(pil_img.size) > 1000:
                scale = 1000 / max(pil_img.size)
                pil_img = pil_img.resize((int(pil_img.size[0] * scale), int(pil_img.size[1] * scale)))
            
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(pil_img)
            pil_img = enhancer.enhance(2.0)
            
            # Sharpen
            pil_img = pil_img.filter(ImageFilter.SHARPEN)
            
            # Get just the central third which usually contains item numbers
            width, height = pil_img.size
            center_img = pil_img.crop((width//4, height//3, 3*width//4, 2*height//3))
            
            # First pass - get just digits with tight constraints
            start_time = time.time()
            digit_config = '--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789'
            digits_text = pytesseract.image_to_string(center_img, config=digit_config)
            logging.info(f"Digit OCR took {time.time() - start_time:.2f} seconds")
            
            # Second pass - get all text but with a shorter timeout
            start_time = time.time()
            general_config = '--psm 4 --oem 3'  # Column mode - often better for receipts
            general_text = pytesseract.image_to_string(pil_img, config=general_config)
            logging.info(f"General OCR took {time.time() - start_time:.2f} seconds")
            
            # Combine results
            combined_text = digits_text + "\n" + general_text
            
            # Cancel the timeout
            signal.alarm(0)
            
            return combined_text
            
        except TimeoutError:
            signal.alarm(0)
            logging.error("Primary OCR processing timed out")
            
            # Fall back to ultra-simplified processing
            try:
                # Very basic approach - read image and just get digits with minimal processing
                img = cv2.imread(image_path, 0)  # Read as grayscale
                if img is None:
                    return "Error: Could not read image"
                
                # Resize to minimum
                h, w = img.shape
                if max(h, w) > 800:
                    scale = 800 / max(h, w)
                    img = cv2.resize(img, (int(w * scale), int(h * scale)))
                
                # Simple thresholding
                _, binary = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY)
                
                # Process center only
                height, width = binary.shape
                center = binary[height//3:2*height//3, width//4:3*width//4]
                
                # Use quickest OCR config
                pytesseract.pytesseract.timeout = 3000  # 3 seconds max
                digit_config = '--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789'
                result = pytesseract.image_to_string(center, config=digit_config)
                
                return result
            except Exception as fallback_error:
                logging.error(f"Fallback OCR also failed: {str(fallback_error)}")
                return "Error: OCR processing failed"
                
        except Exception as inner_error:
            signal.alarm(0)
            logging.error(f"Error in inner OCR processing: {str(inner_error)}")
            return f"Error: OCR processing failed: {str(inner_error)}"
            
    except Exception as outer_error:
        logging.error(f"Error in OCR processing: {str(outer_error)}")
        return f"Error: {str(outer_error)}"

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
