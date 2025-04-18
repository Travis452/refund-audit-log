import cv2
import pytesseract
import re
import logging
import os
import numpy as np
from datetime import datetime

def preprocess_image(image_path):
    """Preprocess the image for better OCR results."""
    # Read the image
    img = cv2.imread(image_path)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply adaptive thresholding - better for varying lighting conditions
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    
    # Apply dilation and erosion to remove noise
    kernel = np.ones((1, 1), np.uint8)
    img_dilation = cv2.dilate(thresh, kernel, iterations=1)
    img_erosion = cv2.erode(img_dilation, kernel, iterations=1)
    
    # Apply Gaussian blur to reduce noise
    processed = cv2.GaussianBlur(img_erosion, (3, 3), 0)
    
    # Apply Otsu's thresholding as final step
    _, processed = cv2.threshold(processed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    return processed

def process_image(image_path):
    """Process the image with OCR to extract text."""
    try:
        # Configure logging
        logging.basicConfig(level=logging.DEBUG)
        logging.info(f"Processing image: {image_path}")
        
        # Check if the image file exists
        if not os.path.exists(image_path):
            logging.error(f"Image file not found: {image_path}")
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        logging.info(f"Image file exists, size: {os.path.getsize(image_path)} bytes")
        
        try:
            # Preprocess the image
            logging.info("Preprocessing image...")
            processed_img = preprocess_image(image_path)
            logging.info("Preprocessing complete")
            
            # Apply OCR
            logging.info("Applying OCR with pytesseract...")
            extracted_text = pytesseract.image_to_string(processed_img)
            logging.info(f"OCR complete, extracted {len(extracted_text)} characters")
            
            # Log the extracted text for debugging
            logging.debug(f"Extracted text from image: {extracted_text[:200]}...")
            
            return extracted_text
        except Exception as inner_e:
            logging.error(f"Error during image processing or OCR: {str(inner_e)}")
            # Try a direct OCR approach without preprocessing as fallback
            logging.info("Attempting direct OCR without preprocessing as fallback...")
            extracted_text = pytesseract.image_to_string(cv2.imread(image_path))
            logging.info(f"Direct OCR complete, extracted {len(extracted_text)} characters")
            return extracted_text
            
    except Exception as e:
        logging.error(f"Error in process_image: {str(e)}")
        raise e

def extract_data_from_text(text):
    """Extract structured data from OCR text."""
    logging.info("Starting data extraction from OCR text")
    logging.debug(f"Text to process: {text[:500]}...")
    
    items = []
    
    # Split text into lines
    lines = text.strip().split('\n')
    logging.info(f"Split text into {len(lines)} lines")
    
    # Special patterns for the receipt format we've observed
    # Based on the image.jpg sample
    audit_receipt_pattern = r'(Member#:|Operator ID:).*?(\d{6,8}).*?Register.*?(\d+\.\d{2}).*?POS Time.*?(\d{2}:\d{2}:\d{2})'
    audit_line_pattern = r'(Member#:|Operator ID:).*?(\d{6,8}).*?(\d+\.\d{2})'
    
    # Fallback patterns
    item_pattern = r'(\d{6,8})'
    price_pattern = r'(\d+\.\d{2})'  # Matches prices like 499.99
    date_pattern = r'(\d{2}/\d{2}/\d{2})'
    time_pattern = r'(\d{2}:\d{2}:\d{2})'
    
    # First look for the report date near the top
    report_date = None
    for i in range(min(10, len(lines))):
        date_match = re.search(date_pattern, lines[i])
        if date_match:
            report_date = date_match.group(1)
            logging.info(f"Found report date: {report_date}")
            break
    
    logging.info("Looking for item data in text")
    
    # First try to match the specific pattern for our receipt
    # Looking for the full audit receipt pattern
    for i, line in enumerate(lines):
        matches = re.search(audit_receipt_pattern, line)
        if matches:
            item_data = {
                'item_number': matches.group(2),
                'price': matches.group(3),
                'date': report_date or '',
                'time': matches.group(4),
                'description': f"Item {matches.group(2)}"
            }
            items.append(item_data)
            logging.info(f"Found item with complete pattern: {item_data}")
    
    # If we found items using the full pattern, return them
    if items:
        logging.info(f"Found {len(items)} items using complete audit receipt pattern")
        return items
    
    # Try to match the simpler pattern
    for i, line in enumerate(lines):
        matches = re.search(audit_line_pattern, line)
        if matches:
            # Try to find time in this line or next
            time_match = re.search(time_pattern, line)
            time_value = ''
            if time_match:
                time_value = time_match.group(1)
            else:
                # Look for time in the next line
                if i < len(lines) - 1:
                    time_match = re.search(time_pattern, lines[i+1])
                    if time_match:
                        time_value = time_match.group(1)
            
            item_data = {
                'item_number': matches.group(2),
                'price': matches.group(3),
                'date': report_date or '',
                'time': time_value,
                'description': f"Item {matches.group(2)}"
            }
            items.append(item_data)
            logging.info(f"Found item with simplified pattern: {item_data}")
    
    # If we found items using the simplified pattern, return them
    if items:
        logging.info(f"Found {len(items)} items using simplified audit receipt pattern")
        return items
    
    # If no items were found, try a different approach - more specific to the Refund Audit format
    logging.info("No items found using audit patterns, trying refund receipt pattern matching")
    
    # Look for rows of text that might contain items
    item_rows = []
    in_item_section = False
    for line in lines:
        # Look for the start of item list section
        if "Item #" in line or "Item/Dept" in line:
            in_item_section = True
            continue
        
        # Skip until we're in the item section
        if not in_item_section:
            continue
        
        # Check if this line could be an item row (contains item number and price)
        item_match = re.search(item_pattern, line)
        price_match = re.search(price_pattern, line)
        
        if item_match and price_match:
            item_rows.append(line)
    
    # Process each potential item row
    for row in item_rows:
        item_match = re.search(item_pattern, row)
        price_match = re.search(price_pattern, row)
        
        if item_match and price_match:
            item_data = {
                'item_number': item_match.group(1),
                'price': price_match.group(1),
                'date': report_date or '',
                'time': '',
                'description': f"Item {item_match.group(1)}"
            }
            items.append(item_data)
    
    # If we found items using item rows pattern, return them
    if items:
        logging.info(f"Found {len(items)} items using item rows pattern")
        return items
    
    # If no items were found yet, try a more generic approach
    logging.info("No items found using specific patterns, trying generic pattern matching")
    
    # Try looking for item numbers paired with prices anywhere in the text
    item_numbers = re.findall(r'(\d{6,8})', text)
    prices = re.findall(r'(\d+\.\d{2})', text)
    
    logging.info(f"Found {len(item_numbers)} potential item numbers")
    logging.info(f"Found {len(prices)} potential prices")
    
    # Find all dates and times regardless of format
    dates = re.findall(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
    times = re.findall(r'(\d{1,2}:\d{2}(?::\d{2})?)', text)
    
    # If we have at least some item numbers and prices, try to pair them
    if item_numbers and prices:
        # For up to 20 items
        count = min(len(item_numbers), len(prices), 20)
        
        # Try to match items and prices that appear close together in the text
        for i in range(count):
            item_number = item_numbers[i]
            # Find the position of this item number in the text
            item_pos = text.find(item_number)
            
            # Find the closest price to this item
            closest_price = None
            closest_distance = float('inf')
            
            for price in prices:
                price_pos = text.find(price)
                distance = abs(price_pos - item_pos)
                
                if distance < closest_distance and distance < 200:  # Within reasonable proximity
                    closest_price = price
                    closest_distance = distance
            
            if closest_price:
                item_data = {
                    'item_number': item_number,
                    'price': closest_price,
                    'date': report_date or (dates[0] if dates else ''),
                    'time': times[0] if times else '',
                    'description': f"Item {item_number}"
                }
                
                # Check if we already have this item to avoid duplicates
                if not any(item['item_number'] == item_number for item in items):
                    items.append(item_data)
        
        logging.info(f"Created {len(items)} items using proximity matching")
    
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
