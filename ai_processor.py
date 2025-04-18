import os
import base64
import json
import logging
from openai import OpenAI
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def encode_image(image_path):
    """Convert image to base64 encoding for API."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error encoding image: {str(e)}")
        raise

def extract_item_numbers_with_ai(image_path):
    """
    Use OpenAI's vision model to extract item numbers and prices from receipt.
    """
    
    # First check if the API key is valid and exists
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("No OpenAI API key found in environment variables")
        return []
    
    try:
        # Encode the image
        base64_image = encode_image(image_path)
        
        # Create prompt for item number extraction
        prompt = """
        Analyze this receipt image and extract the following information:
        1. All item/product numbers (SKU, UPC, item codes)
        2. The price for each item (if visible)
        3. The date and time of the transaction (if visible)
        
        Format your response as a JSON array with each item having these properties:
        {
            "item_number": "the extracted item number",
            "price": "the price of the item (if available)",
            "date": "the date of the receipt (if available)",
            "time": "the time on the receipt (if available)"
        }
        
        Focus specifically on finding product/item numbers which are usually 6-12 digits.
        Don't include other types of numbers (like phone numbers, store numbers, etc).
        If you can't find any item numbers, return an empty array.
        """
        
        try:
            # Call the OpenAI API with proper error handling
            response = client.chat.completions.create(
                model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                            }
                        ]
                    }
                ],
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
        except Exception as api_error:
            # Handle API errors gracefully
            logger.error(f"OpenAI API error: {str(api_error)}")
            
            # Check for quota or rate limit errors
            error_str = str(api_error).lower()
            if "insufficient_quota" in error_str or "rate limit" in error_str or "429" in error_str:
                logger.warning("OpenAI API quota or rate limit exceeded")
            
            # Return empty list to allow fallback to traditional OCR
            return []
        
        # Process the response
        content = response.choices[0].message.content
        logger.info(f"AI response: {content}")
        
        # Parse JSON response
        try:
            parsed_data = json.loads(content)
            if "items" in parsed_data:
                items = parsed_data["items"]
            else:
                # Handle case where the model might directly return an array
                items = parsed_data if isinstance(parsed_data, list) else [parsed_data]
                
            # Normalize data
            result = []
            for item in items:
                item_data = {
                    "item_number": item.get("item_number", ""),
                    "price": item.get("price", ""),
                    "date": item.get("date", ""),
                    "time": item.get("time", ""),
                    "period": "P00"  # Default period
                }
                
                # Clean item number (remove any non-alphanumeric chars except dash)
                item_data["item_number"] = re.sub(r'[^A-Za-z0-9\-]', '', item_data["item_number"])
                
                # Only add items that have an item number
                if item_data["item_number"]:
                    result.append(item_data)
            
            logger.info(f"Extracted {len(result)} items using AI")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing AI response as JSON: {str(e)}")
            # Try to extract data manually if JSON parsing fails
            return extract_fallback(content)
    
    except Exception as e:
        logger.error(f"Error using AI to extract data: {str(e)}")
        raise

def extract_fallback(content):
    """Fallback method if JSON parsing fails."""
    items = []
    
    # Simple pattern matching to extract item numbers and prices
    item_pattern = r'item[_\s]*number["\s:]*([A-Za-z0-9\-]+)'
    price_pattern = r'price["\s:]*(\$?[\d\.]+)'
    date_pattern = r'date["\s:]*([^\n,"]+)'
    time_pattern = r'time["\s:]*([^\n,"]+)'
    
    # Find all item numbers
    item_matches = re.finditer(item_pattern, content, re.IGNORECASE)
    price_matches = re.finditer(price_pattern, content, re.IGNORECASE)
    date_matches = re.finditer(date_pattern, content, re.IGNORECASE)
    time_matches = re.finditer(time_pattern, content, re.IGNORECASE)
    
    # Extract item numbers
    item_numbers = [match.group(1) for match in item_matches]
    prices = [match.group(1) for match in price_matches]
    dates = [match.group(1) for match in date_matches]
    times = [match.group(1) for match in time_matches]
    
    # Match up the data
    for i, item_number in enumerate(item_numbers):
        item_data = {
            "item_number": item_number,
            "price": prices[i] if i < len(prices) else "",
            "date": dates[0] if dates else "",
            "time": times[0] if times else "",
            "period": "P00"  # Default period
        }
        items.append(item_data)
    
    logger.info(f"Extracted {len(items)} items using fallback method")
    return items