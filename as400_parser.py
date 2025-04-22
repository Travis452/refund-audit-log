def parse_as400_audit(file_path):
    """
    Parses fixed-width AS400 audit logs into a structured dictionary.
    """
    data = []
    with open(file_path, "r") as file:
        for line in file:
            if len(line.strip()) < 70:
                continue  # Skip short lines or headers

            entry = {
                "Rec#": line[0:4].strip(),
                "Trn#": line[5:9].strip(),
                "Date": line[10:18].strip(),
                "Tracking#": line[19:32].strip(),
                "Member#": line[33:47].strip(),
                "Item#": line[46:55].strip(),
                "Dept": line[55:59].strip(),
                "Qty": line[59:62].strip(),
                "Tender $": line[67:75].strip(),
                "Saleable": line[76:77].strip(),
                "Refund": line[78:79].strip(),
                "Auditor": line[80:].strip()
            }
            data.append(entry)
    return data
