"""Build synthetic fixtures with the standard library only; never load NLP models."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TARGETS = '''ABA_ROUTING_NUMBER ACCOUNT_ID ADDRESS ADMISSION_DATE AGE API_KEY AUTH_TOKEN AU_ABN AU_ACN AU_MEDICARE AU_TFN BIOMETRIC_ID CARD_CVV CARD_EXPIRY CA_SIN CREDIT_CARD CREDIT_SCORE CRYPTO DATE_OF_BIRTH DATE_OF_DEATH DATE_TIME DE_BSNR DE_FUEHRERSCHEIN DE_HANDELSREGISTER DE_HEALTH_INSURANCE DE_ID_CARD DE_KFZ DE_LANR DE_PASSPORT DE_PLZ DE_SOCIAL_SECURITY DE_TAX_ID DE_TAX_NUMBER DE_VAT_ID DISCHARGE_DATE DRIVER_LICENSE_NUMBER EMAIL EMAIL_ADDRESS EMPLOYEE_ID ES_NIE ES_NIF ES_PASSPORT ETHNICITY FI_PERSONAL_IDENTITY_CODE GENDER GPS_COORDINATES IBAN_CODE ID IMEI INSURANCE_ID IN_AADHAAR IN_GSTIN IN_PAN IN_PASSPORT IN_VEHICLE_REGISTRATION IN_VOTER IP_ADDRESS IT_DRIVER_LICENSE IT_FISCAL_CODE IT_IDENTITY_CARD IT_PASSPORT IT_VAT_CODE KR_BRN KR_DRIVER_LICENSE KR_FRN KR_PASSPORT KR_RRN LICENSE_PLATE LOCATION MAC_ADDRESS MARITAL_STATUS MEDICAL_LICENSE MEDICAL_RECORD_NUMBER NATIONAL_ID_NUMBER NG_NIN NG_VEHICLE_REGISTRATION NRP ORGANIZATION PASSPORT_NUMBER PASSWORD PERSON PHONE_NUMBER PH_TIN PH_UMID PL_PESEL POLITICAL_AFFILIATION PRIVATE_KEY PROFESSIONAL_LICENSE RELIGION SALARY SERIAL_NUMBER SESSION_ID SEXUAL_ORIENTATION SE_ORGANISATIONSNUMMER SE_PERSONNUMMER SG_NRIC_FIN SG_UEN SOCIAL_HANDLE STUDENT_ID SWIFT_BIC TAX_ID_NUMBER TH_TNIN TR_LICENSE_PLATE TR_NATIONAL_ID UK_DRIVING_LICENCE UK_NHS UK_NINO UK_PASSPORT UK_POSTCODE UK_VEHICLE_REGISTRATION URL USERNAME US_ALIEN_NUMBER US_BANK_NUMBER US_DRIVER_LICENSE US_EIN US_ITIN US_MBI US_NPI US_PASSPORT US_SSN US_ZIP_CODE UUID VIN ZA_ID_NUMBER'''.split()
CAT = json.loads((ROOT / 'samples/world_pii_complete.json').read_text())['entity_catalog']
# Additional installed recognizers absent from the older catalog.
body = '27384615'
product = 10
for d in body:
    total = (int(d) + product) % 10 or 10
    product = total * 2 % 11
check = 11 - product
if check == 10:
    check = 0
lanr_body = '273846'
lanr_check = (10 - sum(int(d)*w for d,w in zip(lanr_body,[4,9,4,9,4,9])) % 10) % 10
NEW = {
 'DE_BSNR': ('bsnr', '382738461', 'Installed source: 9 non-zero digits, base score 0.2; no public checksum.'),
 'DE_LANR': ('lanr', lanr_body + str(lanr_check) + '01', 'Installed source checksum: alternating weights 4/9 on first six digits.'),
 'DE_FUEHRERSCHEIN': ('führerschein', 'HH27384615B', 'Installed source: two uppercase letters, eight digits, one uppercase letter/digit; base score 0.35.'),
 'DE_VAT_ID': ('vat', 'DE' + body + str(check), 'Installed source heuristic ISO 7064 Mod 11,10 checksum; not an issuance check.'),
 'PH_UMID': ('umid', '2738-4615290-6', 'Installed source dash-separated 4-7-1 digits, base score 0.5; no checksum.'),
 'ORGANIZATION': ('companyName', 'Silver Pine Technologies', 'Project JSON companyName alias; synthetic organization.'),
 'EMAIL': ('email', 'diagnostic@example.com', 'Registry-only NLP alias: English spaCy does not emit EMAIL; expect EMAIL_ADDRESS instead.'),
 'ID': ('nationalIdNumber', 'TEST-78124563', 'Registry-only NLP alias: English spaCy does not emit ID; expect NATIONAL_ID_NUMBER instead.'),
 'PRIVATE_KEY': ('privateKey', '-----BEGIN RSA PRIVATE KEY-----\nQUJDREVGR0hJSktMTU5PUA==\n-----END RSA PRIVATE KEY-----', 'Synthetic PEM detection fixture, not a usable key.'),
 'EMAIL_ADDRESS': ('email', 'emily.carter@example.com', 'Synthetic address using the reserved example.com domain.'),
 'API_KEY': ('apiKey', 'AKIAIOSFODNN7EXAMPLE', 'AWS-format example identifier; not a usable credential.'),
 'PHONE_NUMBER': ('phoneNumber', '+1-202-555-0147', 'Synthetic labeled phone test value.'),
 'CREDIT_CARD': ('credit card number', '4111 1111 1111 1111', 'Synthetic payment test number; no transaction is performed.'),
}
LABELS = {'PERSON':'fullName','LOCATION':'location','NRP':'nationality','EMAIL_ADDRESS':'email','DATE_TIME':'timestamp', 'AGE':'age', 'PASSWORD':'password'}
ALTERNATES = {
 'EMAIL':['EMAIL_ADDRESS'], 'ID':['NATIONAL_ID_NUMBER'],
 'IN_GSTIN':['TAX_ID_NUMBER'], 'DE_VAT_ID':['TAX_ID_NUMBER'],
 'IN_PASSPORT':['PASSPORT_NUMBER'], 'US_DRIVER_LICENSE':['DRIVER_LICENSE_NUMBER'],
 'UK_PASSPORT':['PASSPORT_NUMBER','US_PASSPORT'], 'ES_PASSPORT':['PASSPORT_NUMBER'],
 'IT_PASSPORT':['PASSPORT_NUMBER'], 'KR_PASSPORT':['PASSPORT_NUMBER','US_PASSPORT'],
 'AGE':['DATE_TIME'], 'NRP':['RELIGION','POLITICAL_AFFILIATION'],
 'DE_LANR':['US_PASSPORT'], 'DE_BSNR':['US_PASSPORT'],
}
payload = {}
rows = []
for entity in TARGETS:
    historical = None
    if entity in NEW:
        label, value, source = NEW[entity]
    else:
        catalog_key = entity + ' (custom)' if entity + ' (custom)' in CAT else entity
        historical = CAT[catalog_key]
        example = historical['examples'][0]
        value = example['value']
        sentence = example.get('in_a_sentence', '')
        label = sentence[len('Please note the '):sentence.index(value)].strip() if sentence.startswith('Please note the ') else LABELS.get(entity,entity.lower())
        label = LABELS.get(entity,label)
        source = 'Historical synthetic catalog: samples/world_pii_complete.json, entity_catalog.'
    # Stable ordinary values for deterministic structured field matching.
    if entity == 'PERSON': value = 'Sarah Johnson'
    if entity == 'AGE': value = 28
    payload[entity] = {label:value}
    weak = historical is not None and historical.get('reachable_at_default_threshold_0_5') is False
    if entity == 'DE_BSNR': weak = True
    rows.append({
        'target_type':entity,'field_path':[entity,label],'value':value,
        'source':source,
        'current_validation':'Not run: no model loading, Docker or API calls.',
        'historical_best_score':historical.get('best_presidio_score_seen') if historical else None,
        'historical_below_default_threshold':weak,
        'possible_alternate_types':ALTERNATES.get(entity,[]),
        'diagnostic_only':entity in {'EMAIL','ID'},
        'expectation':'Registered label not emitted by the English NLP model.' if entity in {'EMAIL','ID'} else 'Target recognition probe; exact class is not guaranteed under default collapse/threshold.',
    })
pretty = json.dumps(payload,ensure_ascii=False,indent=2)+'\n'
mini = json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n'
assert len(payload)==len(TARGETS)==125
assert len(pretty.encode())<=20000
(OUT/'payload.json').write_text(pretty)
(OUT/'minified.json').write_text(mini)
(OUT/'manifest.json').write_text(json.dumps({'registered_types':125,'synthetic':True,'notice':'Generated test fixtures; checksum/format plausibility does not prove issuance, ownership or real-world validity. Never use these as production credentials.','test_status':'No current runtime verification performed.','cases':rows},ensure_ascii=False,indent=2)+'\n')
print(f'125 entries; pretty {len(pretty.encode())} bytes; minified {len(mini.encode())} bytes')
