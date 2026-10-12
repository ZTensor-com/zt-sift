"""Build synthetic fixtures. No service credentials are stored in this folder."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
cases = []

def add(name, text, values=(), category="positive", query=None, status=200, content_type="text/plain"):
    expected = []
    cursor = 0
    for value, entities in values:
        at = text.index(value, cursor)
        expected.append({"text": value, "entities": entities.split("|"), "start": at, "end": at + len(value)})
        cursor = at + len(value)
    cases.append(dict(name=name, text=text, expected=expected, category=category,
                      query=query or {}, status=status, content_type=content_type))

sample = '''Sarah Johnson (age: 34, gender: female, ethnicity: Hispanic, marital status: married, sexual orientation: bisexual, religion: Catholic, political affiliation: Democrat, credit score: 742), born on March 14, 1989. She lives at 742 Evergreen Terrace, Springfield, IL 62704 (ZIP code 62704-1234); mail goes to PO Box 4521, Austin, TX 78701. Call (201) 555-0123 or 212-555-0187. Salary: $85,000; employer EIN 12-3456789; employee ID EMP-016973; student ID S87749056; customer ID CUST-884213. Passport number 075977035, driver license number L8227257, ID card number 98765432, taxpayer ID 98-7654321, alien registration number A123456789, nursing license number RN-445566. Bank account number 3982583440, CVV 737, expiry 08/28, SWIFT code DEUTDEFF500, Ethereum wallet 0x52908400098527886E0F7030069857D2E4169EE7. Medical record number MRN 00482913, insurance policy number ZXC123456789, admitted on March 2, 2024, discharge date: 03/09/2024; her father died on 11/02/2023. Username: sarah_j89, password is Sup3rS3cret!42, follow @sarah_j89, API key AKIAIOSFODNN7EXAMPLE, bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r, session ID 3f2a9c1e7b4d8a6f0c2e5b1d9a7f4c3e, fingerprint hash 9f86d081884c7d659a2feaa0c55ad015; a leaked file begins with -----BEGIN RSA PRIVATE KEY-----. Her car VIN is 1HGCM82633A004352 with license plate 7ABC123; phone IMEI 490154203237518, device serial number SN48210937, device 3f2504e0-4f89-41d3-9a0c-0305e82c3301, last seen at coordinates 40.71278, -74.00594.
'''
sample_values = [
    ("Sarah Johnson","PERSON"),("34","AGE"),("female","GENDER"),("Hispanic","ETHNICITY"),
    ("married","MARITAL_STATUS"),("bisexual","SEXUAL_ORIENTATION"),("Catholic","RELIGION"),
    ("Democrat","POLITICAL_AFFILIATION"),("742","CREDIT_SCORE"),("March 14, 1989","DATE_OF_BIRTH"),
    ("742 Evergreen Terrace, Springfield, IL 62704","ADDRESS"),("62704-1234","US_ZIP_CODE"),
    ("PO Box 4521, Austin, TX 78701","ADDRESS"),("(201) 555-0123","PHONE_NUMBER"),("212-555-0187","PHONE_NUMBER"),
    ("$85,000","SALARY"),("12-3456789","US_EIN"),("EMP-016973","EMPLOYEE_ID"),("S87749056","STUDENT_ID"),
    ("CUST-884213","ACCOUNT_ID"),("075977035","US_PASSPORT|PASSPORT_NUMBER"),("L8227257","DRIVER_LICENSE_NUMBER"),
    ("98765432","NATIONAL_ID_NUMBER"),("98-7654321","TAX_ID_NUMBER"),("A123456789","US_ALIEN_NUMBER"),
    ("RN-445566","PROFESSIONAL_LICENSE"),("3982583440","US_BANK_NUMBER"),("737","CARD_CVV"),("08/28","CARD_EXPIRY"),
    ("DEUTDEFF500","SWIFT_BIC"),("0x52908400098527886E0F7030069857D2E4169EE7","CRYPTO"),
    ("00482913","MEDICAL_RECORD_NUMBER"),("ZXC123456789","INSURANCE_ID"),("March 2, 2024","ADMISSION_DATE"),
    ("03/09/2024","DISCHARGE_DATE"),("11/02/2023","DATE_OF_DEATH"),("sarah_j89","USERNAME"),
    ("Sup3rS3cret!42","PASSWORD"),("@sarah_j89","SOCIAL_HANDLE"),("AKIAIOSFODNN7EXAMPLE","API_KEY"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r","AUTH_TOKEN"),
    ("3f2a9c1e7b4d8a6f0c2e5b1d9a7f4c3e","SESSION_ID"),("9f86d081884c7d659a2feaa0c55ad015","BIOMETRIC_ID"),
    ("-----BEGIN RSA PRIVATE KEY-----","PRIVATE_KEY"),("1HGCM82633A004352","VIN"),("7ABC123","LICENSE_PLATE"),
    ("490154203237518","IMEI"),("SN48210937","SERIAL_NUMBER"),("3f2504e0-4f89-41d3-9a0c-0305e82c3301","UUID"),
    ("40.71278, -74.00594","GPS_COORDINATES")]
add("user_sample",sample,sample_values,"sample")
add("user_sample_raw",sample,sample_values,"sample_raw",{"collapse":"false"})

# One isolated positive for every project-defined entity.
canonical = [
 ("AGE","age: 34","34"),("GENDER","gender: female","female"),("ETHNICITY","ethnicity: Hispanic","Hispanic"),
 ("MARITAL_STATUS","marital status: married","married"),("SEXUAL_ORIENTATION","sexual orientation: bisexual","bisexual"),
 ("RELIGION","religion: Catholic","Catholic"),("POLITICAL_AFFILIATION","political affiliation: Democrat","Democrat"),
 ("CREDIT_SCORE","credit score: 742","742"),("DATE_OF_BIRTH","DOB: 1989-03-14","1989-03-14"),
 ("ADDRESS","Address: 742 Evergreen Terrace, Springfield, IL 62704","742 Evergreen Terrace, Springfield, IL 62704"),
 ("US_ZIP_CODE","zip: 62704-1234","62704-1234"),("PHONE_NUMBER","Call (201) 555-0123","(201) 555-0123"),
 ("SALARY","Salary: $85,000","$85,000"),("US_EIN","EIN: 12-3456789","12-3456789"),
 ("EMPLOYEE_ID","employee ID: EMP-016973","EMP-016973"),("STUDENT_ID","student ID: S87749056","S87749056"),
 ("ACCOUNT_ID","customer ID: CUST-884213","CUST-884213"),("US_PASSPORT","US passport: 075977035","075977035"),
 ("PASSPORT_NUMBER","passport: K1234567","K1234567"),("DRIVER_LICENSE_NUMBER","driver license: L8227257","L8227257"),
 ("NATIONAL_ID_NUMBER","national ID: 98765432","98765432"),("TAX_ID_NUMBER","taxpayer ID: 98-7654321","98-7654321"),
 ("US_ALIEN_NUMBER","alien registration number: A123456789","A123456789"),
 ("PROFESSIONAL_LICENSE","nursing license: RN-445566","RN-445566"),("US_BANK_NUMBER","bank account: 3982583440","3982583440"),
 ("CARD_CVV","CVV: 737","737"),("CARD_EXPIRY","expiry: 08/28","08/28"),("SWIFT_BIC","SWIFT: DEUTDEFF500","DEUTDEFF500"),
 ("CRYPTO","Ethereum wallet: 0x52908400098527886E0F7030069857D2E4169EE7","0x52908400098527886E0F7030069857D2E4169EE7"),
 ("MEDICAL_RECORD_NUMBER","MRN: 00482913","00482913"),("INSURANCE_ID","insurance policy: ZXC123456789","ZXC123456789"),
 ("ADMISSION_DATE","admitted on March 2, 2024","March 2, 2024"),("DISCHARGE_DATE","discharge date: 03/09/2024","03/09/2024"),
 ("DATE_OF_DEATH","died on 11/02/2023","11/02/2023"),("USERNAME","username: sarah_j89","sarah_j89"),
 ("PASSWORD","password: Sup3rS3cret!42","Sup3rS3cret!42"),("SOCIAL_HANDLE","follow @sarah_j89","@sarah_j89"),
 ("API_KEY","API key: AKIAIOSFODNN7EXAMPLE","AKIAIOSFODNN7EXAMPLE"),
 ("AUTH_TOKEN","bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r","eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r"),
 ("SESSION_ID","session ID: 3f2a9c1e7b4d8a6f0c2e5b1d9a7f4c3e","3f2a9c1e7b4d8a6f0c2e5b1d9a7f4c3e"),
 ("BIOMETRIC_ID","fingerprint hash: 9f86d081884c7d659a2feaa0c55ad015","9f86d081884c7d659a2feaa0c55ad015"),
 ("PRIVATE_KEY","-----BEGIN RSA PRIVATE KEY-----","-----BEGIN RSA PRIVATE KEY-----"),
 ("VIN","VIN: 1HGCM82633A004352","1HGCM82633A004352"),("LICENSE_PLATE","license plate: 7ABC123","7ABC123"),
 ("IMEI","IMEI: 490154203237518","490154203237518"),("SERIAL_NUMBER","serial number: SN48210937","SN48210937"),
 ("UUID","device 3f2504e0-4f89-41d3-9a0c-0305e82c3301","3f2504e0-4f89-41d3-9a0c-0305e82c3301"),
 ("GPS_COORDINATES","coordinates 40.71278, -74.00594","40.71278, -74.00594")]
for entity,text,value in canonical:
    types = "US_PASSPORT|PASSPORT_NUMBER" if entity=="US_PASSPORT" else entity
    add("canonical_"+entity,text,[(value,types)],"canonical")

variants = [
 ("lower_address","address: 742 evergreen terrace, springfield, il 62704","742 evergreen terrace, springfield, il 62704","ADDRESS"),
 ("upper_address","ADDRESS: 742 EVERGREEN TERRACE, SPRINGFIELD, IL 62704","742 EVERGREEN TERRACE, SPRINGFIELD, IL 62704","ADDRESS"),
 ("india_address","Address: Flat 4B, 12 MG Road, Bengaluru, Karnataka 560001","Flat 4B, 12 MG Road, Bengaluru, Karnataka 560001","ADDRESS"),
 ("lower_name","Please contact sarah johnson tomorrow.","sarah johnson","PERSON"),
 ("hindi_name","नाम: आरव शर्मा","आरव शर्मा","PERSON"),
 ("short_password","password: abc","abc","PASSWORD"),
 ("dictionary_password","password: secret","secret","PASSWORD"),
 ("quoted_passphrase",'password: "correct horse battery staple"',"correct horse battery staple","PASSWORD"),
 ("punctuation_password","password: hunter2!.","hunter2!","PASSWORD"),
 ("escaped_password",'{"password": "pass\\\"word123!"}',"pass\\\"word123!","PASSWORD"),
 ("short_username","username: jo","jo","USERNAME"),
 ("hyphenated_social","follow @sarah-j89","@sarah-j89","SOCIAL_HANDLE"),
 ("plain_salary","salary: 85000","85000","SALARY"),
 ("indian_salary","salary: ₹12,50,000","₹12,50,000","SALARY"),
 ("spaced_bank","bank account: 1234 5678 9012","1234 5678 9012","US_BANK_NUMBER"),
 ("hyphen_student","student ID: STU-123456","STU-123456","STUDENT_ID"),
 ("alphanumeric_employee","employee ID: E9AB12345","E9AB12345","EMPLOYEE_ID"),
 ("json_camel_birth",'{"dateOfBirth":"1989-03-14"}',"1989-03-14","DATE_OF_BIRTH"),
 ("json_camel_medical",'{"medicalRecordNumber":"MRN-00482913"}',"MRN-00482913","MEDICAL_RECORD_NUMBER"),
 ("polite_label","password is actually Sup3rS3cret!42","Sup3rS3cret!42","PASSWORD"),
 ("incomplete_dob","DOB: March 14","March 14","DATE_OF_BIRTH"),
 ("uuid_v7","device 01890f3e-7c4a-7cc0-98c4-dc0c0c07398f","01890f3e-7c4a-7cc0-98c4-dc0c0c07398f","UUID"),
 ("integer_gps","GPS coordinates: 40, -74","40, -74","GPS_COORDINATES"),
 ("antimeridian_gps","coordinates: 45.00000, 180.00000","45.00000, 180.00000","GPS_COORDINATES"),
 ("two_decimal_gps","coordinates: 40.71, -74.00","40.71, -74.00","GPS_COORDINATES"),
 ("full_private_key","-----BEGIN PRIVATE KEY-----\nQUJDREVGRw==\n-----END PRIVATE KEY-----","-----BEGIN PRIVATE KEY-----\nQUJDREVGRw==\n-----END PRIVATE KEY-----","PRIVATE_KEY"),
 ("long_api_key","api key: "+"a"*240,"a"*240,"API_KEY"),
 ("long_session","session ID: "+"b"*140,"b"*140,"SESSION_ID"),
 ("duplicate_emails","jane@example.com and jane@example.com","jane@example.com","EMAIL_ADDRESS"),
 ("emoji_offsets","😀 Contact jane@example.com.","jane@example.com","EMAIL_ADDRESS"),
]
for name,text,value,entity in variants:
    add(name,text,[(value,entity)],"variant")
if cases[-2]['name']=='duplicate_emails':
    e=cases[-2]['expected'][0].copy(); e['start']=cases[-2]['text'].rindex(e['text']);e['end']=e['start']+len(e['text']); cases[-2]['expected'].append(e)

# Exhaustive-negative fixtures: no PII is intended, including invalid formats.
negatives = {
 "ordinary_prose":"Please reset your password. The user is logged in. Our policy number is required. Page 12 of 40.",
 "product_orgs":"NASA, IBM and 3M announced a partnership.",
 "filler_label":"password: unavailable", "negated_password":"There is no password: hunter2xyz!", 
 "negated_username":"Do not use username: sarah_j89", 
 "invalid_vin":"VIN: 1HGCM82633A004353", "invalid_imei":"IMEI: 490154203237519",
 "invalid_date":"DOB: 99/99/9999", "invalid_leap_date":"DOB: February 30, 2024",
 "invalid_expiry":"expiry: 19/28", "invalid_cvv":"CVV: 12", "invalid_credit_score":"credit score: 899",
 "out_of_range_age":"age: 999", "invalid_years_old":"999 years old", "newborn_age":"age: 0",
 "out_of_range_gps":"coordinates: 90.12345, 74.12345", "numeric_pair":"totals: 12.345, 67.890",
 "non_pii_ids":"Build ID 123456789; invoice 1234567890; ticket 2125550187; version 1.234, 5.678.",
 "label_substrings":"key passwordlessauthentication is enabled; tokenizationabcdefghijklmnop was optimized.",
 "invalid_card":"card: 4111 1111 1111 1112", "invalid_ssn":"SSN: 000-00-0000",
 "invalid_ip":"IP: 999.999.999.999", "invalid_postal":"zip: 6270412345",
}
# Organization names are valid detections but some may be silently suppressed.
for name,text in negatives.items():
    if name in ('product_orgs','newborn_age','negated_password','negated_username'):
        continue  # separate policy/coverage cases rather than false-positive labels
    add(name,text,category="negative")
add("real_short_organizations",negatives['product_orgs'],[("NASA","ORGANIZATION"),("IBM","ORGANIZATION"),("3M","ORGANIZATION")],"variant")
add("newborn_age",negatives['newborn_age'],[("0","AGE")],"variant")
# Values in a negated statement can still be sensitive; include them as positives.
add("negated_password",negatives['negated_password'],[("hunter2xyz!","PASSWORD")],"variant")
add("negated_username",negatives['negated_username'],[("sarah_j89","USERNAME")],"variant")

# Important stock formats absent from the supplied text.
for name,text,value,entity in [
 ("email","Email: jane@example.com","jane@example.com","EMAIL_ADDRESS"),
 ("card","Card: 4111 1111 1111 1111","4111 1111 1111 1111","CREDIT_CARD"),
 ("ssn","SSN: 219-09-9999","219-09-9999","US_SSN"),
 ("iban","IBAN: GB82 WEST 1234 5698 7654 32","GB82 WEST 1234 5698 7654 32","IBAN_CODE"),
 ("ipv4","IP address: 192.168.1.1","192.168.1.1","IP_ADDRESS"),
 ("ipv6","IP address: 2001:db8::1","2001:db8::1","IP_ADDRESS"),
 ("mac","MAC address: 00:1A:2B:3C:4D:5E","00:1A:2B:3C:4D:5E","MAC_ADDRESS"),
 ("url","URL: https://example.com/profile","https://example.com/profile","URL"),
 ("in_pan","PAN: ABCPE1234F","ABCPE1234F","IN_PAN"),
 ("uk_nino","National Insurance: QQ 12 34 56 C","QQ 12 34 56 C","UK_NINO"),
]:
    # QQ is intentionally invalid, use an accepted non-real synthetic prefix.
    if name=='uk_nino': text="National Insurance: AB 12 34 56 C";value="AB 12 34 56 C"
    add("stock_"+name,text,[(value,entity)],"stock")

for name,body,ct,status,query in [
 ("empty","","text/plain",400,{}),("whitespace"," \n ","text/plain",400,{}),
 ("json_null","null","application/json",400,{}),("json_list","[]","application/json",400,{}),
 ("json_number","42","application/json",400,{}),("json_bad","{","application/json",400,{}),
 ("json_nonstring",'{"text":42}',"application/json",400,{}),
 ("json_valid",'{"text":"jane@example.com"}',"application/json",200,{}),
 ("threshold_nan","hello","text/plain",400,{"threshold":"nan"}),
 ("threshold_high","hello","text/plain",400,{"threshold":"1.01"}),
 ("unknown_entities","hello","text/plain",400,{"entities":"BOGUS"}),
 ("empty_entities","jane@example.com","text/plain",200,{"entities":""}),
 ("bad_collapse","hello","text/plain",400,{"collapse":"maybe"}),
 ("over_limit","x"*20001,"text/plain",413,{}),
 ("byte_limit_unicode","😀"*5001,"text/plain",413,{})]:
    add("request_"+name,body,category="request",query=query,status=status,content_type=ct)

OUT.joinpath('cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
OUT.joinpath('user_sample.txt').write_text(sample)
print(f'{len(cases)} fixtures; {len(canonical)} custom entity positives; sample {len(sample_values)} expected spans')
