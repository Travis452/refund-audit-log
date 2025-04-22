import fitz  # PyMuPDF

def process_pdf(file_path):
    data = {}
    with fitz.open(file_path) as doc:
        full_text = ""
        for page in doc:
            full_text += page.get_text()

    # Optional: clean or parse it
    for line in full_text.splitlines():
        if ":" in line:
            parts = line.split(":", 1)
            key = parts[0].strip()
            value = parts[1].strip()
            data[key] = value

    return data
