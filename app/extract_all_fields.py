from fuzzywuzzy import fuzz
import re

def extract_all_fields(ocr_result, image):
    image_path = ocr_result['input_path']
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    height, width = image.shape[:2]
    x_center, y_center = width // 2, height // 2

    def classify_point(x, y):
        if x > x_center and y < y_center:
            return 'Q1'
        elif x < x_center and y < y_center:
            return 'Q2'
        elif x < x_center and y > y_center:
            return 'Q3'
        elif x > x_center and y > y_center:
            return 'Q4'
        return 'Mixed'

    # Define known label strings for fuzzy matching
    LABELS = {
        "CHIEF": ["CHIEF", "CHIES", "CHEIF", "CHEF","CHILS"],
        "DISTRICT": ["DISTRICT", "DISTNICT", "DIST", "DISRICT"],
        "VILLAGE": ["VILLAGE", "VILLG", "VILAGE", "VILL"],
        "SEX": ["SEX", "SAX", "S3X"],
        "REGISTRATION DATE": ["REGISTRATIONDATE", "REGISTRATIOWDATE", "REGDATE"],
        "DATE OF BIRTH": ["DATEOFBIRTH", "BIRTHDATE", "DOB"],
        "CARD NUMBER": ["CARDNO", "CARDNUMBER"],
    }

    def is_similar(word, label_group):
        return any(fuzz.partial_ratio(word.upper(), l.upper()) > 80 for l in label_group)

    rec_texts = ocr_result['rec_texts']
    rec_polys = ocr_result['dt_polys']

    # Annotate texts with quadrants and centers
    items = []
    for text, poly in zip(rec_texts, rec_polys):
        avg_x = sum(x for x, y in poly) / len(poly)
        avg_y = sum(y for x, y in poly) / len(poly)
        quadrant = classify_point(avg_x, avg_y)
        items.append({'text': text.strip().upper(), 'x': avg_x, 'y': avg_y, 'quadrant': quadrant})

    # Sort items top to bottom, left to right
    items.sort(key=lambda i: (i['y'], i['x']))

    # Step-by-step parsing state
    dob = None
    registration_date = None
    card_number = None
    sex = None
    district = None
    village = None
    chief = None
    first_name = None

    q1_items = [i for i in items if i['quadrant'] == 'Q1']
    q2_items = [i for i in items if i['quadrant'] == 'Q2']
    q3_items = [i for i in items if i['quadrant'] == 'Q3']
    q4_items = [i for i in items if i['quadrant'] == 'Q4']

    # Extract DOB (from Q2, match date pattern)
    date_regex = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")
    for item in q2_items:
        if date_regex.match(item['text']):
            dob = item['text']
            break

    # Extract Registration Date (from Q4)
    for item in q4_items:
        if date_regex.match(item['text']):
            registration_date = item['text']
            break

    # Extract Card Number (from Q1)
    for item in q1_items:
        if re.fullmatch(r"[A-Z]?\s?\d{6,}", item['text']):
            card_number = item['text'].replace(" ", "")
            if not card_number.upper().startswith("Z"):
                card_number = "Z" + card_number
            break

    # Extract Sex (Q1)
    for item in q1_items:
        t = item['text'].strip().rstrip(".") #OCR might add a '.', which can mess up the detection logic
        if fuzz.partial_ratio(t, "MALE") >= 80:
            sex = "Male"
            break
        elif fuzz.partial_ratio(t, "FEMALE") >= 80:
            sex = "Female"
            break


    # Extract First Name (from Q2): exclude English-like terms
    IGNORE = [
        "REPUBLIC", "OF", "NATIONAL", "REGISTRATION", "FULLNAME", "FULL NAME",
        "DATE", "BIRTH", "PLACE", "FATHER", "MOTHER", "SEX"
    ]
    candidate_names = [i['text'] for i in q2_items if all(fuzz.partial_ratio(i['text'], ign) < 80 for ign in IGNORE)]
    if candidate_names:
        first_name = candidate_names[0]

    # Extract village and chief (from Q3)
    q3_words = [i for i in q3_items if all(fuzz.partial_ratio(i['text'], ign) < 85 for ign in (
        LABELS['CHIEF'] + LABELS['VILLAGE'] + [
            "MARKS", "SPECIAL", "IF", "THIS", "CARD", "IS", "FOUND", "PLEASE", "OR"
        ]
    ))]

    if q3_words:
        # Village is closest to y_center (x-axis)
        village_candidate = min(q3_words, key=lambda i: abs(i['y'] - y_center))
        village = village_candidate['text']
        # Chief = other word(s)
        other_chief = [i['text'] for i in q3_words if i['text'] != village]
        for word in other_chief:
            if fuzz.ratio(word, "NIL") < 80:
                chief = word
                break

    # Extract district (Q4) via label
    for idx, item in enumerate(q4_items[:-1]):
        if is_similar(item['text'], LABELS["DISTRICT"]):
            next_text = q4_items[idx + 1]['text']
            if next_text and next_text.isalpha():
                district = next_text
                break

    # Fallback for district: pick any standalone word not labeled as CHIEF/VILLAGE/NIL
    if not district:
        for item in q4_items:
            if item['text'].isalpha() and fuzz.partial_ratio(item['text'], "NIL") < 80:
                if not is_similar(item['text'], LABELS["CHIEF"] + LABELS["VILLAGE"]):
                    district = item['text']
                    break

    # Extract chief (override with Q4 if CHIEF label found)
    for idx, item in enumerate(q4_items[:-1]):
        if is_similar(item['text'], LABELS["CHIEF"]):
            next_text = q4_items[idx + 1]['text']
            if next_text and fuzz.ratio(next_text, "NIL") < 80:
                chief = next_text
                break

    return {
        'date_of_birth': dob,
        'registration_date': registration_date,
        'district_name': district,
        'first_name': first_name,
        'sex': sex,
        'card_number': card_number,
        'village_name': village,
        'chief_name': chief,
    }