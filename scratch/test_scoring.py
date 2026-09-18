import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from backend.social_finder import generate_handle_variations, score_candidate

# Test 1: rdameesha
sp, st = generate_handle_variations("rdameesha@gmail.com")
all_v = sp + st
score, reasons = score_candidate(
    {"handle": "dameesha_09", "platform": "instagram"},
    "𝓓𝓪𝓶𝓮𝓮𝓼𝓱𝓪 ✨ (@dameesha_09) • Instagram photos and videos",
    "",
    all_v,
    None,
    None
)
print("rdameesha -> dameesha_09:", score, reasons)

# Test 2: momina0 -> _momina0
sp, st = generate_handle_variations("mominawaqar18@gmail.com", "Momina Waqar", "momina0")
all_v = sp + st
score, reasons = score_candidate(
    {"handle": "_momina0", "platform": "instagram"},
    "momina:) (@_momina0) • Instagram photos and videos",
    "",
    all_v,
    "Momina Waqar",
    "Faisalabad, Pakistan"
)
print("momina -> _momina0:", score, reasons)

# Test 3: ahtishamdilawar -> ahtisham.v2
sp, st = generate_handle_variations("ahtishamdilawar@gmail.com", "Ahtisham Dilawar")
all_v = sp + st
score, reasons = score_candidate(
    {"handle": "ahtisham.v2", "platform": "instagram"},
    "𝘼𝙝𝙩𝙞𝙨𝙝𝙖𝙢 (@ahtisham.v2) • Instagram photos and videos",
    "",
    all_v,
    "Ahtisham Dilawar",
    None
)
print("ahtishamdilawar -> ahtisham.v2:", score, reasons)

# Test 4: ahtishamdilawar -> ahtisham.v3
score, reasons = score_candidate(
    {"handle": "ahtisham.v3", "platform": "instagram"},
    "(@ahtisham.v3) • Instagram photos and videos",
    "",
    all_v,
    "Ahtisham Dilawar",
    None
)
print("ahtishamdilawar -> ahtisham.v3:", score, reasons)
