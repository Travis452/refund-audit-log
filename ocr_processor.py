import cv2
import pytesseract
import re
import logging
import os
import numpy as np
from datetime import datetime

# This function is now integrated into process_image

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
            # Simpler preprocessing approach to avoid memory issues
            logging.info("Preprocessing image...")
            
            # Read the image
            img = cv2.imread(image_path)
            
            # Resize image if it's too small (helps improve OCR)
            height, width = img.shape[:2]
            if width < 1000:
                scale_factor = 1000 / width
                img = cv2.resize(img, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
            
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Method 1: Adaptive thresholding - works well for receipts
            processed_img = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
            
            # Save the processed version
            temp_dir = '/tmp/preprocessed'
            os.makedirs(temp_dir, exist_ok=True)
            cv2.imwrite(f"{temp_dir}/processed.png", processed_img)
            
            logging.info("Preprocessing complete")
            
            # Try with receipt-specific configuration
            receipt_config = '--psm 4 --oem 3'
            try:
                logging.info("Applying OCR with receipt-specific configuration...")
                extracted_text = pytesseract.image_to_string(processed_img, config=receipt_config)
                
                # If it contains key phrases from our receipt, use it
                if "Member#:" in extracted_text or "Operator ID:" in extracted_text:
                    logging.info("Receipt-specific OCR successful")
                    return extracted_text
            except Exception as config_error:
                logging.error(f"Error with receipt config: {str(config_error)}")
            
            # Fall back to standard OCR if receipt-specific failed
            logging.info("Applying standard OCR...")
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
