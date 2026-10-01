"""
constants.py
------------
Centralized constants, datasets, lookup dictionaries, and header profiles for EmailLookup.
Consolidates all in-memory static tables to eliminate code duplication and drift.
"""

from typing import Dict, Set, List, Tuple

# ==============================================================================
# 1. HTTP HEADERS & CRAWLER USER AGENTS
# ==============================================================================

BROWSER_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Sec-Ch-Ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

CRAWLER_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

TWITTER_HEADERS: Dict[str, str] = {
    "User-Agent": "Twitterbot/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

LI_CRAWLER_HEADERS: Dict[str, str] = {
    "User-Agent": "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ==============================================================================
# 2. DOMAIN & EMAIL TYPO RULES
# ==============================================================================

PERSONAL_DOMAINS: Set[str] = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "rocketmail.com",
    "hotmail.com", "outlook.com", "live.com", "msn.com", "icloud.com", "me.com",
    "mac.com", "protonmail.com", "proton.me", "aol.com", "zoho.com", "mail.com",
    "gmx.com", "gmx.net", "yandex.com", "yandex.ru", "tutanota.com", "tutamail.com",
    "fastmail.com", "hushmail.com"
}

INVALID_TYPO_DOMAINS: Set[str] = {
    "gmil.com", "gmai.com", "gamil.com", "gmial.com", "gmaill.com", "gmal.com",
    "yaho.com", "yahooo.com", "yaho.co", "hotmial.com", "hotmaill.com", "outlok.com",
    "outloo.com", "microsft.com", "micosoft.com", "gmail.con", "yahoo.con", "hotmail.con",
    "outlook.con", "icloud.con"
}

KNOWN_DOMAIN_TYPOS: Dict[str, str] = {
    "gmil.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmial.com": "gmail.com",
    "gmaill.com": "gmail.com",
    "gmal.com": "gmail.com",
    "yaho.com": "yahoo.com",
    "yahooo.com": "yahoo.com",
    "yaho.co": "yahoo.com",
    "hotmial.com": "hotmail.com",
    "hotmaill.com": "hotmail.com",
    "outlok.com": "outlook.com",
    "outloo.com": "outlook.com",
    "microsft.com": "microsoft.com",
    "micosoft.com": "microsoft.com",
}


# ==============================================================================
# 3. NAME PARSING, TITLES, ROLES & LEETSPEAK
# ==============================================================================

TITLE_PREFIXES: Set[str] = {
    "ch", "chaudhry", "chaudhary", "dr", "engr", "eng", "mr", "ms", "mrs", 
    "prof", "syed", "sh", "sk", "sheikh", "md", "muhd", "malik", "adv", "al", "el", "haj", "haji"
}

ROLE_SUFFIXES: Set[str] = {
    "hr", "dev", "qa", "ceo", "cto", "cfo", "coo", "cmo", "admin", "recruiter", 
    "sales", "support", "help", "jobs", "hiring", "team", "legal", "ops", "design", "tech", "official"
}

LEET_REPLACEMENTS: List[Tuple[str, str]] = [
    ("33", "ee"),
    ("00", "oo"),
    ("3", "e"),
    ("0", "o"),
    ("1", "i"),
    ("4", "a"),
    ("5", "s"),
    ("7", "t"),
]

# Comprehensive global first names dictionary (Western, South Asian, Middle Eastern,
# East Asian, European, Hispanic, African) for deterministic username splitting.
COMMON_FIRST_NAMES: Set[str] = {
    # South Asian / Middle Eastern / Islamic Names
    "fahad", "ahmad", "ahmed", "saad", "noman", "nouman", "nauman", "ali", "hamza", "usman", "osman",
    "bilal", "hassan", "hasan", "hussain", "zain", "omer", "umar", "faisal", "farhan", 
    "kashif", "tariq", "asif", "dameesha", "ahtisham", "atisam", "dilawar", "hameed",
    "ghaffar", "rashid", "tahir", "nasir", "amir", "aamir", "sami", "haris", "junaid",
    "waseem", "wasim", "naveed", "navid", "arshad", "akram", "aslam", "iqbal", "anwar",
    "akhtar", "latif", "mahmood", "mehmood", "butt", "dar", "bhatti", "rana", "khan",
    "chaudhry", "malik", "sheikh", "syed", "shah", "javed", "javaid", "siddiqui",
    "qureshi", "ansari", "farooqi", "abbasi", "mirza", "baig", "mughal", "rehman",
    "rahman", "aziz", "khalid", "sultan", "alam", "raza", "ashraf", "munir", "zafar",
    "nawaz", "sarwar", "liaquat", "abid", "sajid", "majid", "zahid", "shahzad",
    "khurram", "shahbaz", "tanveer", "tanvir", "waheed", "wahid", "yousaf", "yusuf",
    "yaqoob", "ayub", "arouba", "ayesha", "fatima", "zainab", "maryam", "mariam",
    "hira", "sana", "iqra", "amna", "sadia", "mahnoor", "anmol", "noor", "rabia",
    "sidra", "kinza", "alishba", "hafsa", "laiba", "bisma", "aiman", "nimra",
    "bushra", "sumaira", "shazia", "rubina", "farzana", "tahira", "samina", "yasmeen",
    "shabnam", "nasreen", "parveen", "uzma", "fauzia", "fozia", "saima", "asifa",
    "nida", "fariha", "hina", "madiha", "kiran", "mehwish", "komal", "natasha", "sonia",
    "haseeb", "rauf", "tauqeer", "tauqir", "touqeer", "touqir", "shafiq", "shafique",
    "mohid", "faraz", "shayan", "mubashir", "mohsin", "sharafat", "adnan", "imran",
    "kamran", "zeeshan", "waqas", "danish", "rizwan", "irfan", "salman", "mustafa",
    "murtaza", "ibrahim", "ismail", "taha", "yaseen", "zubair", "shoaib", "sohail",
    "talha", "danyal", "daniyal", "danish", "huzaifa", "subhan", "rehan", "rohan",

    # Western / European / American Names
    "erik", "john", "david", "michael", "james", "robert", "william", "richard",
    "thomas", "charles", "daniel", "matthew", "anthony", "mark", "donald", "steven",
    "paul", "andrew", "joshua", "kenneth", "kevin", "brian", "george", "timothy",
    "ronald", "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas", "eric",
    "jonathan", "stephen", "larry", "justin", "scott", "brandon", "benjamin", "samuel",
    "gregory", "alexander", "frank", "patrick", "raymond", "jack", "dennis", "jerry",
    "tyler", "aaron", "jose", "adam", "nathan", "henry", "douglas", "zachary", "peter",
    "kyle", "walter", "ethan", "jeremy", "harold", "keith", "christian", "roger", "noah",
    "gerald", "carl", "terry", "sean", "austin", "arthur", "lawrence", "jesse", "dylan",
    "bryan", "joe", "jordan", "billy", "albert", "bruce", "willie", "gabriel", "logan",
    "alan", "juan", "wayne", "roy", "ralph", "randy", "eugene", "vincent", "russell",
    "louis", "philip", "bobby", "johnny", "bradley", "collison", "alex", "alexander",
    "satya", "sundar", "guido", "guy", "linus", "bill", "steve", "elon", "mark",
    "jeff", "sam", "satyanadella", "larry", "sergey", "tim", "jensen", "danielle",
    "katie", "sarah", "laszlo", "horacio", "lucas", "oliver", "liam", "elijah",
    "mason", "lucas", "oliver", "henry", "sebastian", "aidan", "owen", "samuel",
    "emily", "olivia", "emma", "charlotte", "amelia", "sophia", "isabella", "ava",
    "mia", "evelyn", "harper", "camila", "gianna", "abigail", "luna", "ella",
    "elizabeth", "sofia", "emily", "avery", "mila", "scarlett", "eleanor", "madison",
    "chloe", "layla", "penelope", "aria", "grace", "zoey", "nora", "riley", "lily",

    # Hispanic / Latin Names
    "carlos", "alejandro", "javier", "diego", "manuel", "miguel", "jorge", "luis",
    "fernando", "roberto", "ricardo", "eduardo", "rafael", "mario", "sergio", "antonio",
    "pedro", "pablo", "ruben", "hector", "arturo", "victor", "raul", "oscar", "guillermo",
    "maria", "ana", "laura", "carmen", "patricia", "isabel", "marta", "elena", "lucia",

    # East Asian / International Tech Names
    "chen", "wang", "zhang", "liu", "yang", "huang", "zhao", "wu", "zhou", "xu",
    "sun", "ma", "zhu", "hu", "guo", "he", "gao", "lin", "luo", "zheng", "liang",
    "xie", "song", "tang", "xu", "han", "feng", "deng", "cao", "peng", "zeng",
    "siddharth", "arjun", "rohit", "rahul", "aditya", "varun", "vikram", "anand",
    "karthik", "pranav", "suresh", "ramesh", "rajesh", "sunil", "deepak", "manish",
    "priya", "pooja", "ananya", "neha", "shreya", "divya", "sneha", "kavita", "swati"
}


# ==============================================================================
# 4. SYSTEM & RESERVED URL SLUGS
# ==============================================================================

RESERVED_SYSTEM_SLUGS: Set[str] = {
    "login", "signin", "signup", "register", "auth", "oauth", "password", "reset",
    "logout", "help", "support", "contact", "about", "privacy", "terms", "tos",
    "legal", "security", "jobs", "careers", "press", "blog", "news", "status",
    "api", "developer", "docs", "feed", "explore", "search", "notifications",
    "messages", "settings", "profile", "account", "user", "users", "home",
    "sharer", "share", "intent", "recover", "pages", "groups", "events", "watch",
    "photo", "photos", "video", "videos", "reel", "reels", "posts", "stories",
    "direct", "accounts", "tag", "live", "trending", "discover", "pin", "pins",
    "board", "boards", "today", "shop", "ideas", "topics", "collection", "dir",
    "pub", "school", "company", "pulse", "learning", "i", "status", "statuses"
}

GENERIC_WORDS: Set[str] = {
    "user", "profile", "official", "real", "the", "page", "channel", "account",
    "fan", "club", "team", "app", "dev", "studio", "group", "media", "news",
    "blog", "daily", "world", "online", "net", "org", "live", "music", "art"
}


# ==============================================================================
# 5. GEOLOCATION, TIMEZONES & COUNTRY MAPPINGS
# ==============================================================================

US_STATES: Dict[str, str] = {
    "al": "United States", "ak": "United States", "az": "United States",
    "ar": "United States", "ca": "United States", "co": "United States",
    "ct": "United States", "de": "United States", "fl": "United States",
    "ga": "United States", "hi": "United States", "id": "United States",
    "il": "United States", "in": "United States", "ia": "United States",
    "ks": "United States", "ky": "United States", "la": "United States",
    "me": "United States", "md": "United States", "ma": "United States",
    "mi": "United States", "mn": "United States", "ms": "United States",
    "mo": "United States", "mt": "United States", "ne": "United States",
    "nv": "United States", "nh": "United States", "nj": "United States",
    "nm": "United States", "ny": "United States", "nc": "United States",
    "nd": "United States", "oh": "United States", "ok": "United States",
    "or": "United States", "pa": "United States", "ri": "United States",
    "sc": "United States", "sd": "United States", "tn": "United States",
    "tx": "United States", "ut": "United States", "vt": "United States",
    "va": "United States", "wa": "United States", "wv": "United States",
    "wi": "United States", "wy": "United States", "dc": "United States"
}

KNOWN_CITIES: Dict[str, str] = {
    "london": "United Kingdom", "manchester": "United Kingdom", "birmingham": "United Kingdom",
    "edinburgh": "United Kingdom", "glasgow": "United Kingdom", "leeds": "United Kingdom",
    "bristol": "United Kingdom", "cambridge": "United Kingdom", "oxford": "United Kingdom",
    "paris": "France", "lyon": "France", "marseille": "France", "toulouse": "France",
    "berlin": "Germany", "munich": "Germany", "frankfurt": "Germany", "hamburg": "Germany", "cologne": "Germany",
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada", "ottawa": "Canada", "calgary": "Canada",
    "sydney": "Australia", "melbourne": "Australia", "brisbane": "Australia", "perth": "Australia",
    "karachi": "Pakistan", "lahore": "Pakistan", "islamabad": "Pakistan", "rawalpindi": "Pakistan",
    "faisalabad": "Pakistan", "multan": "Pakistan", "peshawar": "Pakistan", "quetta": "Pakistan",
    "sialkot": "Pakistan", "gujranwala": "Pakistan",
    "mumbai": "India", "delhi": "India", "bangalore": "India", "bengaluru": "India",
    "hyderabad": "India", "chennai": "India", "pune": "India", "kolkata": "India",
    "tokyo": "Japan", "osaka": "Japan", "kyoto": "Japan",
    "beijing": "China", "shanghai": "China", "shenzhen": "China", "guangzhou": "China",
    "dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates",
    "riyadh": "Saudi Arabia", "jeddah": "Saudi Arabia",
    "amsterdam": "Netherlands", "rotterdam": "Netherlands",
    "stockholm": "Sweden", "oslo": "Norway", "copenhagen": "Denmark", "helsinki": "Finland",
    "madrid": "Spain", "barcelona": "Spain", "rome": "Italy", "milan": "Italy",
    "zurich": "Switzerland", "geneva": "Switzerland", "vienna": "Austria", "brussels": "Belgium",
    "singapore": "Singapore", "seoul": "South Korea", "taipei": "Taiwan",
    "new york": "United States", "san francisco": "United States", "seattle": "United States",
    "los angeles": "United States", "chicago": "United States", "austin": "United States",
    "boston": "United States", "denver": "United States", "atlanta": "United States"
}

COUNTRY_CANONICAL: Dict[str, str] = {
    "us": "United States", "usa": "United States", "uk": "United Kingdom",
    "gb": "United Kingdom", "uae": "United Arab Emirates", "pk": "Pakistan",
    "in": "India", "ca": "Canada", "au": "Australia", "de": "Germany",
    "fr": "France", "nl": "Netherlands", "br": "Brazil", "ru": "Russia",
    "cn": "China", "jp": "Japan", "kr": "South Korea", "es": "Spain",
    "it": "Italy", "mx": "Mexico", "id": "Indonesia", "tr": "Turkey",
    "sa": "Saudi Arabia", "za": "South Africa", "eg": "Egypt", "ng": "Nigeria"
}

ALL_COUNTRIES: Set[str] = {
    "afghanistan", "albania", "algeria", "andorra", "angola", "argentina", "armenia", "australia",
    "austria", "azerbaijan", "bahamas", "bahrain", "bangladesh", "barbados", "belarus", "belgium",
    "belize", "benin", "bhutan", "bolivia", "bosnia and herzegovina", "botswana", "brazil", "brunei",
    "bulgaria", "burkina faso", "burundi", "cambodia", "cameroon", "canada", "chile", "china",
    "colombia", "costa rica", "croatia", "cuba", "cyprus", "czech republic", "denmark", "dominican republic",
    "ecuador", "egypt", "el salvador", "estonia", "ethiopia", "fiji", "finland", "france",
    "georgia", "germany", "ghana", "greece", "guatemala", "haiti", "honduras", "hungary",
    "iceland", "india", "indonesia", "iran", "iraq", "ireland", "israel", "italy", "jamaica",
    "japan", "jordan", "kazakhstan", "kenya", "kuwait", "latvia", "lebanon", "libya", "lithuania",
    "luxembourg", "madagascar", "malaysia", "maldives", "mali", "malta", "mexico", "monaco",
    "mongolia", "montenegro", "morocco", "mozambique", "myanmar", "nepal", "netherlands", "new zealand",
    "nicaragua", "nigeria", "norway", "oman", "pakistan", "panama", "paraguay", "peru", "philippines",
    "poland", "portugal", "qatar", "romania", "russia", "rwanda", "saudi arabia", "senegal", "serbia",
    "singapore", "slovakia", "slovenia", "somalia", "south africa", "south korea", "spain", "sri lanka",
    "sudan", "sweden", "switzerland", "syria", "taiwan", "tajikistan", "tanzania", "thailand",
    "tunisia", "turkey", "uganda", "ukraine", "united arab emirates", "united kingdom", "united states",
    "uruguay", "uzbekistan", "venezuela", "vietnam", "yemen", "zambia", "zimbabwe"
}

TZ_REGIONS: Dict[int, str] = {
    -10: "United States (Hawaii)",
    -8:  "United States (Pacific)",
    -7:  "United States (Mountain)",
    -6:  "United States (Central)",
    -5:  "United States (Eastern)",
    -4:  "Canada (Atlantic)",
    -3:  "Brazil / Argentina",
    0:   "United Kingdom / Western Europe",
    1:   "Central Europe / West Africa",
    2:   "Eastern Europe / Central Africa",
    3:   "Middle East / East Africa",
    4:   "United Arab Emirates / Caucasus",
    5:   "Pakistan / Uzbekistan",
    5.5: "India / Sri Lanka",
    6:   "Bangladesh / Kazakhstan",
    7:   "Southeast Asia (Thailand/Vietnam)",
    8:   "China / Singapore / Perth",
    9:   "Japan / South Korea",
    10:  "Australia (Eastern)",
    12:  "New Zealand",
}
