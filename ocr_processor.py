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
    
    # Apply thresholding
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    
    # Apply dilation and erosion to remove noise
    kernel = np.ones((1, 1), np.uint8)
    img_dilation = cv2.dilate(thresh, kernel, iterations=1)
    img_erosion = cv2.erode(img_dilation, kernel, iterations=1)
    
    # Invert back
    processed = cv2.bitwise_not(img_erosion)
    
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
    
    # Regular expressions for data extraction
    item_number_pattern = r'Item/Dept\s*:\s*(\d+)'
    description_pattern = r'Description\s*:\s*([A-Za-z0-9\s]+)'
    price_pattern = r'(\d+\.\d{2})'  # Matches prices like 499.99
    date_pattern = r'Date\s*:\s*(\d{2}/\d{2}/\d{2})'
    time_pattern = r'POS Time\s*:\s*(\d{2}:\d{2}:\d{2})'
    
    logging.info("Looking for item data in text")
    
    # For each line that seems to contain item data
    for i, line in enumerate(lines):
        # Check for lines that could contain item data
        if "Member#:" in line or "Operator ID:" in line:
            try:
                # Extract item details from the current line and surrounding lines
                item_data = {}
                
                # Look for item number and description
                item_match = re.search(r'(\d{6,8})', line)
                if item_match:
                    item_data['item_number'] = item_match.group(1)
                else:
                    # Try to find item number in surrounding lines
                    for offset in [-2, -1, 1, 2]:
                        if i + offset >= 0 and i + offset < len(lines):
                            item_match = re.search(r'(\d{6,8})', lines[i + offset])
                            if item_match:
                                item_data['item_number'] = item_match.group(1)
                                break
                
                # Look for price
                price_match = re.search(price_pattern, line)
                if price_match:
                    item_data['price'] = price_match.group(1)
                else:
                    # Try to find price in surrounding lines
                    for offset in [-2, -1, 1, 2]:
                        if i + offset >= 0 and i + offset < len(lines):
                            price_match = re.search(price_pattern, lines[i + offset])
                            if price_match:
                                item_data['price'] = price_match.group(1)
                                break
                
                # Look for date
                date_match = re.search(r'Date\s*:\s*(\d{2}/\d{2}/\d{2})', line)
                if not date_match:
                    date_match = re.search(r'(\d{2}/\d{2}/\d{2})', line)
                if date_match:
                    item_data['date'] = date_match.group(1)
                else:
                    # Try to find date in surrounding lines
                    for offset in [-2, -1, 1, 2]:
                        if i + offset >= 0 and i + offset < len(lines):
                            date_match = re.search(r'Date\s*:\s*(\d{2}/\d{2}/\d{2})', lines[i + offset])
                            if not date_match:
                                date_match = re.search(r'(\d{2}/\d{2}/\d{2})', lines[i + offset])
                            if date_match:
                                item_data['date'] = date_match.group(1)
                                break
                
                # Look for time
                time_match = re.search(r'POS Time\s*:\s*(\d{2}:\d{2}:\d{2})', line)
                if not time_match:
                    time_match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                if time_match:
                    item_data['time'] = time_match.group(1)
                else:
                    # Try to find time in surrounding lines
                    for offset in [-2, -1, 1, 2]:
                        if i + offset >= 0 and i + offset < len(lines):
                            time_match = re.search(r'POS Time\s*:\s*(\d{2}:\d{2}:\d{2})', lines[i + offset])
                            if not time_match:
                                time_match = re.search(r'(\d{2}:\d{2}:\d{2})', lines[i + offset])
                            if time_match:
                                item_data['time'] = time_match.group(1)
                                break
                
                # Only add if we have at least an item number and price
                if 'item_number' in item_data and 'price' in item_data:
                    # Add missing fields with empty values
                    for field in ['item_number', 'price', 'date', 'time']:
                        if field not in item_data:
                            item_data[field] = ''
                    
                    # Try to extract a description if available
                    desc_match = None
                    for offset in [-2, -1, 0, 1, 2]:
                        if i + offset >= 0 and i + offset < len(lines):
                            desc_line = lines[i + offset]
                            if "Description" in desc_line:
                                desc_parts = desc_line.split("Description")
                                if len(desc_parts) > 1:
                                    desc_match = desc_parts[1].strip()
                                    break
                    
                    if desc_match:
                        item_data['description'] = desc_match
                    else:
                        item_data['description'] = f"Item {item_data['item_number']}"
                    
                    items.append(item_data)
            except Exception as e:
                logging.error(f"Error extracting data from line {i}: {str(e)}")
                continue
    
    # If no items were found, try a different approach
    if not items:
        logging.info("No items found using primary method, trying fallback pattern matching")
        
        # Try a more relaxed approach by looking for any digit sequences that could be item numbers
        item_numbers = re.findall(r'(\d{5,8})', text)
        prices = re.findall(r'(\d+\.\d{2})', text)
        dates = re.findall(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
        times = re.findall(r'(\d{1,2}:\d{2}(?::\d{2})?)', text)
        
        logging.info(f"Found {len(item_numbers)} potential item numbers")
        logging.info(f"Found {len(prices)} potential prices")
        logging.info(f"Found {len(dates)} potential dates")
        logging.info(f"Found {len(times)} potential times")
        
        # If we have at least item numbers and prices, create items
        if item_numbers and prices:
            # Match as many items as we can
            count = min(len(item_numbers), len(prices))
            for i in range(count):
                item_data = {
                    'item_number': item_numbers[i],
                    'price': prices[i],
                    'description': f"Item {item_numbers[i]}"
                }
                
                # Add date and time if available
                if i < len(dates):
                    item_data['date'] = dates[i]
                else:
                    item_data['date'] = ''
                    
                if i < len(times):
                    item_data['time'] = times[i]
                else:
                    item_data['time'] = ''
                
                items.append(item_data)
            
            logging.info(f"Created {count} items using fallback method")
        
        # If still no items, try an even more aggressive pattern match
        if not items:
            logging.info("Trying most aggressive pattern matching")
            # Look for patterns like: ItemNumber Price Date Time
            pattern = r'(\d{6,8}).*?(\d+\.\d{2}).*?(\d{2}/\d{2}/\d{2}).*?(\d{2}:\d{2}:\d{2})'
            matches = re.findall(pattern, text)
            
            for match in matches:
                items.append({
                    'item_number': match[0],
                    'price': match[1],
                    'date': match[2],
                    'time': match[3],
                    'description': f"Item {match[0]}"
                })
            
            logging.info(f"Found {len(matches)} items using aggressive pattern matching")
    
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
    
    return items
