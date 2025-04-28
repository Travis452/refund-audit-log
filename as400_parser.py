def parse_as400_audit(file_path):
    data = []
    with open(file_path, "r") as file:
        for line in file:
            if len(line.strip()) < 70:
                continue  # Skip short lines or headers

            date_str = line[10:18].strip()  # <-- For calculating Period
            period = "P00"
            if date_str and len(date_str) >= 2:
                month = date_str[0:2]
                if month.isdigit():
                    period = f"P{month.zfill(2)}"

            entry = {
                "Rec#": line[0:4].strip(),
                "Trn#": line[5:9].strip(),
                "Date": date_str,
                "Tracking#": line[19:32].strip(),
                "Member#": line[33:47].strip(),
                "Item#": line[48:55].strip(),
                "Dept": line[56:59].strip(),
                "Qty": line[60:63].strip(),
                "Tender $": line[64:72].strip(),
                "Saleable": line[73:74].strip(),
                "Refund": line[75:76].strip(),
                "Auditor": line[77:].strip(),
                "Period": period  # <-- NEW FIELD!
            }
            data.append(entry)
    return data
