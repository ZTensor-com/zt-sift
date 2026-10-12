"""Five made-up US documents. Each expected item is (text as it appears, what it is)."""
DOCUMENTS = {
    "customer onboarding": ("""Hi team, please onboard our new customer Sarah Johnson (date of birth 03/14/1989). She lives at 742 Evergreen Terrace, Springfield, IL 62704 and can be reached on (415) 555-0132 or sarah.johnson@example.com. Her SSN is 536-90-4399 and her ITIN is 912-73-4567. Passport number 912803456, driver license number D1234567. Her employer, Acme Corp, uses EIN 12-3456789. Payment: Visa card 4111 1111 1111 1111, expiry 08/28, CVV 737. Bank account number 000123456789 with ABA routing number 021000021. Login username sarah_j89, password Sup3rS3cret!42, API key api_key_7f3a9c2e81b44d6fa0c5e1d92b7a4c38. Crypto wallet 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa. Logged in from IP 192.168.10.45, device MAC 00:1A:2B:3C:4D:5E, profile https://example.com/u/sarah. Her colleague Mike Davis (mike.davis@acme.com) will follow up on Monday at 5 PM.""", [
        ("Sarah Johnson", "person name"), ("03/14/1989", "date of birth"),
        ("742 Evergreen Terrace, Springfield, IL 62704", "street address"), ("(415) 555-0132", "phone number"),
        ("sarah.johnson@example.com", "email"), ("536-90-4399", "social security number"), ("912-73-4567", "ITIN"),
        ("912803456", "passport number"), ("D1234567", "driver's license"), ("Acme Corp", "organization"),
        ("12-3456789", "EIN"), ("4111 1111 1111 1111", "credit card"), ("737", "card CVV"),
        ("000123456789", "bank account number"), ("021000021", "ABA routing number"), ("sarah_j89", "username"),
        ("Sup3rS3cret!42", "password"), ("api_key_7f3a9c2e81b44d6fa0c5e1d92b7a4c38", "API key"),
        ("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa", "crypto wallet"), ("192.168.10.45", "IP address"),
        ("00:1A:2B:3C:4D:5E", "MAC address"), ("https://example.com/u/sarah", "URL"), ("Mike Davis", "person name"),
        ("mike.davis@acme.com", "email")]),
    "support chat": ("Hi, this is Michael Chen. My account email is m.chen88@gmail.com and you can call me on 212-555-0187. I was charged twice on my card 5500 0000 0000 0004 and my billing address is 1600 Pennsylvania Avenue NW, Washington, DC 20500. Please refund me quickly.", [
        ("Michael Chen", "person name"), ("m.chen88@gmail.com", "email"), ("212-555-0187", "phone number"),
        ("5500 0000 0000 0004", "credit card"), ("1600 Pennsylvania Avenue NW, Washington, DC 20500", "street address")]),
    "HR record": ("Employee record: Priya Patel, born 07/22/1992, SSN 489-36-8350, works at Globex Corporation. Direct deposit: routing number 011401533, account number 4400123987. Driver license N1234567 issued in New York. Work email priya.patel@globex.com.", [
        ("Priya Patel", "person name"), ("07/22/1992", "date of birth"), ("489-36-8350", "social security number"),
        ("Globex Corporation", "organization"), ("011401533", "ABA routing number"), ("4400123987", "bank account number"),
        ("N1234567", "driver's license"), ("priya.patel@globex.com", "email")]),
    "developer log": ("Security alert: user jdoe_42 logged in with password hunter2Bravo! from 203.0.113.77. Token ghp_16C7e42F292c6912E7710c838347Ae178B4a was used. Contact admin@initech.io or open https://portal.initech.io/users/jdoe_42 for details.", [
        ("jdoe_42", "username"), ("hunter2Bravo!", "password"), ("203.0.113.77", "IP address"),
        ("ghp_16C7e42F292c6912E7710c838347Ae178B4a", "API token"), ("admin@initech.io", "email"),
        ("https://portal.initech.io/users/jdoe_42", "URL")]),
    "payment request": ("Please wire 5,000 dollars to Daniel O'Connor, passport number 543210987, who lives at 88 Maple Street, Austin, TX 78701. His ITIN is 900-70-1234. Use account 7788991122 with routing 026009593 at Bank of America.", [
        ("Daniel O'Connor", "person name"), ("543210987", "passport number"), ("88 Maple Street, Austin, TX 78701", "street address"),
        ("900-70-1234", "ITIN"), ("7788991122", "bank account number"), ("026009593", "ABA routing number"),
        ("Bank of America", "organization")]),
}
