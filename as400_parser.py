import logging

# Configure logger for this module
logger = logging.getLogger(__name__)


def parse_as400_audit(file_path):
    """
    Parses fixed-width AS400 audit logs into structured dictionaries.
    Emits debug output on the first valid line to help verify column positions.
    """
    data = []
    with open(file_path, "r") as file:
        for i, line in enumerate(file):
            # Skip very short or header lines
            if len(line.strip()) < 70:
                continue

            # Emit debug output on the first data line
            if i == 0:
                logger.debug(f"raw line (len={len(line)}): {repr(line)}")
                marker = "".join(str(j % 10) for j in range(len(line)))
                logger.debug(f" idx: {marker}")

            # Extract date and determine period (e.g., "P04")
            date_str = line[10:18].strip()
            period = f"P{date_str[:2].zfill(2)}" if date_str[:2].isdigit() else "P00"

            entry = {
                "Rec#": line[0:4].strip(),
                "Trn#": line[5:9].strip(),
                "Date": date_str,
                "Tracking#": line[19:32].strip(),
                "Member#": line[33:47].strip(),
                "Item#": line[48:59].strip(),
                "Dept": line[59:63].strip(),
                "Qty": line[64:66].strip(),
                "Tender $": line[67:75].strip(),
                "Saleable": line[76:77].strip(),
                "Refund": line[78:79].strip(),
                "Auditor": line[80:].strip(),
                "Period": period
            }

            # Debug output for field alignment
            if i == 0:
                logger.debug(f"parsed Item# → '{entry['Item#']}'")
                logger.debug(f"parsed Dept   → '{entry['Dept']}'")

            data.append(entry)

    return data
