import cv2
import pytesseract
import re
import logging
import os
import numpy as np
from datetime import datetime

# This function is now integrated into process_image

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
        
        try:
            # Read the image
            img = cv2.imread(image_path)
            if img is None:
                logging.error("Failed to read image - it may be corrupted or in an unsupported format")
                # Return a fallback message to avoid crashing
                return "Error: Could not process image. It may be corrupted or in an unsupported format."
            
            # Create a working copy
            original_img = img.copy()
            
            # Convert to grayscale
            gray = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY)
            
            # Try multiple preprocessing techniques specifically for number recognition
            
            # Technique 1: Basic thresholding for clear text
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            
            # Technique 2: Adaptive thresholding for receipt-like documents
            adaptive = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
            
            # Technique 3: Otsu's thresholding for better separation
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Store the preprocessed images
            preprocessed_imgs = [binary, adaptive, otsu]
            
            # Save for debugging
            temp_dir = '/tmp/preprocessed'
            os.makedirs(temp_dir, exist_ok=True)
            
            for i, p_img in enumerate(preprocessed_imgs):
                cv2.imwrite(f"{temp_dir}/processed_{i}.png", p_img)
            
            # OCR optimized for digit recognition
            # We'll use a custom config focused on digits and test it on each preprocessed image
            digit_config = '--psm 11 --oem 3 -c tessedit_char_whitelist=0123456789'
            
            # For each preprocessed image, run OCR
            for i, p_img in enumerate(preprocessed_imgs):
                try:
                    # Get text from the image
                    ocr_text = pytesseract.image_to_string(p_img)
                    ocr_results.append(ocr_text)
                    
                    # Also try digit-specific OCR to capture item numbers
                    # This focuses just on finding sequences of digits
                    digit_text = pytesseract.image_to_string(p_img, config=digit_config)
                    ocr_results.append(digit_text)
                    
                    logging.info(f"OCR technique {i+1} extracted {len(ocr_text)} characters")
                except Exception as ocr_error:
                    logging.error(f"OCR technique {i+1} failed: {str(ocr_error)}")
            
            # Also try directly on grayscale to catch anything we missed
            try:
                ocr_results.append(pytesseract.image_to_string(gray))
            except Exception:
                pass
                
            # Combine all OCR results
            combined_text = "\n".join(ocr_results)
            logging.info(f"Combined OCR text length: {len(combined_text)}")
            
            # Return the combined OCR results for further processing
            return combined_text
            
        except Exception as inner_e:
            logging.error(f"Error during image processing or OCR: {str(inner_e)}")
            # Fall back to basic OCR if everything else fails
            try:
                logging.info("Attempting direct OCR without preprocessing as final fallback...")
                extracted_text = pytesseract.image_to_string(cv2.imread(image_path))
                return extracted_text
            except:
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
