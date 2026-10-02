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
    # Major Global Consumer Webmails
    "gmail.com", "googlemail.com", "google.com",
    "yahoo.com", "ymail.com", "rocketmail.com", "yahoo.co.uk", "yahoo.fr", "yahoo.de", "yahoo.es", "yahoo.it", "yahoo.ca", "yahoo.com.au", "yahoo.co.in", "yahoo.co.jp", "yahoo.ne.jp", "ybb.ne.jp",
    "hotmail.com", "hotmail.co.uk", "hotmail.fr", "hotmail.es", "hotmail.it", "hotmail.de", "hotmail.ca", "hotmail.com.au",
    "outlook.com", "outlook.co.uk", "outlook.fr", "outlook.de", "outlook.es", "outlook.it", "outlook.ca", "outlook.com.au",
    "live.com", "live.co.uk", "live.fr", "live.de", "live.es", "live.it", "live.ca", "msn.com", "passport.com", "windowslive.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "aim.com", "zoho.com", "zohomail.com",
    "mail.com", "email.com", "usa.com", "post.com", "dr.com", "consultant.com", "myself.com",
    "gmx.com", "gmx.net", "gmx.de", "gmx.at", "gmx.ch",
    "yandex.com", "yandex.ru", "yandex.by", "yandex.kz", "yandex.ua", "ya.ru", "mail.ru", "bk.ru", "inbox.ru", "list.ru", "rambler.ru",

    # Privacy, Developer & Indie Email Providers
    "hey.com", "protonmail.com", "proton.me", "pm.me", "protonmail.ch",
    "tuta.com", "tutanota.com", "tutanota.de", "tutamail.com", "tuta.io", "keemail.me",
    "fastmail.com", "fastmail.fm", "fastmail.net", "fastmail.org", "fastmail.to", "fastmail.co.uk",
    "hushmail.com", "hush.com", "duck.com", "simplelogin.com", "simplelogin.io", "simplelogin.co",
    "anonaddy.me", "addy.io", "mozmail.com", "firefox.com", "relay.firefox.com",
    "skiff.com", "skiff.me", "mailfence.com", "disroot.org", "cock.li", "riseup.net", "autistici.org",
    "runbox.com", "posteo.de", "posteo.net", "mailbox.org", "ctemplar.com", "startmail.com", "infomaniak.com",

    # European & Regional Providers
    "web.de", "t-online.de", "freenet.de", "arcor.de", "1und1.de",
    "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr", "laposte.net", "numericable.fr", "neuf.fr",
    "libero.it", "virgilio.it", "alice.it", "tin.it", "fastwebnet.it", "tiscali.it", "tiscali.co.uk",
    "terra.es", "telefónica.es", "ono.com", "ya.com",
    "uol.com.br", "bol.com.br", "terra.com.br", "ig.com.br", "globo.com", "globomail.com", "sapo.pt",
    "onet.pl", "wp.pl", "interia.pl", "o2.pl", "poczta.fm",
    "seznam.cz", "centrum.cz", "volny.cz", "atlas.cz", "post.cz", "email.cz",
    "freemail.hu", "citromail.hu", "indamail.hu", "vipmail.hu",
    "abv.bg", "mail.bg", "ukr.net", "i.ua", "meta.ua",
    "inbox.lv", "inbox.lt", "inbox.ee", "mail.ee",

    # Asian Regional & Consumer Webmails
    "163.com", "126.com", "yeah.net", "qq.com", "foxmail.com", "sina.com", "sina.cn", "sohu.com", "tom.com", "aliyun.com", "139.com", "189.cn", "wo.cn",
    "naver.com", "daum.net", "hanmail.net", "nate.com",
    "rediffmail.com", "indiatimes.com", "sify.com", "vsnl.net",

    # Major ISP & Telecom Consumer Webmails
    "comcast.net", "xfinity.com", "sbcglobal.net", "att.net", "bellsouth.net", "swbell.net", "pacbell.net", "prodigy.net", "nvbell.net", "flash.net", "ameritech.net",
    "verizon.net", "cox.net", "charter.net", "spectrum.net", "roadrunner.com", "rr.com", "twc.com", "earthlink.net", "mindspring.com", "juno.com", "netzero.net",
    "frontier.com", "windstream.net", "centurylink.net", "embarqmail.com", "q.com",
    "btinternet.com", "btopenworld.com", "virginmedia.com", "blueyonder.co.uk", "ntlworld.com", "sky.com", "talktalk.net", "plus.net",
    "bigpond.com", "bigpond.net.au", "optusnet.com.au", "telstra.com", "tpg.com.au", "iinet.net.au", "ozemail.com.au",
    "shaw.ca", "rogers.com", "telus.net", "sympatico.ca", "bell.net", "videotron.ca", "cogeco.ca"
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

# Comprehensive global first names dataset categorized by worldwide region for
# deterministic username compound splitting (e.g. "alexanderbrown" -> "Alexander Brown").
COMMON_FIRST_NAMES: Set[str] = {
    # -------------------------------------------------------------------------
    # 1. SOUTH ASIAN & ISLAMIC (Pakistani, Indian, Bangladeshi, Arab, Persian, Afghan)
    # -------------------------------------------------------------------------
    "fahad", "ahmad", "ahmed", "saad", "noman", "nouman", "nauman", "ali", "hamza", "usman", "osman",
    "bilal", "hassan", "hasan", "hussain", "hussein", "zain", "zayn", "omer", "umar", "faisal", "farhan", 
    "kashif", "tariq", "asif", "dameesha", "ahtisham", "atisam", "dilawar", "hameed", "abdul", "abdullah",
    "ghaffar", "rashid", "tahir", "nasir", "amir", "aamir", "sami", "samir", "haris", "haroon", "junaid",
    "waseem", "wasim", "naveed", "navid", "arshad", "akram", "aslam", "iqbal", "anwar", "waqar", "zubair",
    "akhtar", "latif", "mahmood", "mehmood", "butt", "dar", "bhatti", "rana", "khan", "qureshi", "ansari",
    "chaudhry", "malik", "sheikh", "syed", "shah", "javed", "javaid", "siddiqui", "abbasi", "mirza", "baig",
    "mughal", "rehman", "rahman", "aziz", "khalid", "sultan", "alam", "raza", "ashraf", "munir", "zafar",
    "nawaz", "sarwar", "liaquat", "abid", "sajid", "majid", "zahid", "shahzad", "khurram", "shahbaz",
    "tanveer", "tanvir", "waheed", "wahid", "yousaf", "yusuf", "yaqoob", "ayub", "arouba", "ayesha",
    "fatima", "zainab", "maryam", "mariam", "hira", "sana", "iqra", "amna", "sadia", "mahnoor", "anmol",
    "noor", "rabia", "sidra", "kinza", "alishba", "hafsa", "laiba", "bisma", "aiman", "nimra", "bushra",
    "sumaira", "shazia", "rubina", "farzana", "tahira", "samina", "yasmeen", "shabnam", "nasreen", "parveen",
    "uzma", "fauzia", "fozia", "saima", "asifa", "nida", "fariha", "hina", "madiha", "kiran", "mehwish",
    "komal", "natasha", "sonia", "haseeb", "rauf", "tauqeer", "tauqir", "touqeer", "touqir", "shafiq",
    "shafique", "mohid", "faraz", "shayan", "mubashir", "mohsin", "sharafat", "adnan", "imran", "kamran",
    "zeeshan", "waqas", "danish", "rizwan", "irfan", "salman", "mustafa", "murtaza", "ibrahim", "ismail",
    "taha", "yaseen", "shoaib", "sohail", "talha", "danyal", "daniyal", "huzaifa", "subhan", "rehan", "rohan", "rohaan", "roaan",
    "arham", "ayaan", "rayyan", "azlan", "musa", "isa", "dawud", "dawood", "idrees", "ilyas", "yahya",
    "areeb", "azhar", "babar", "dawar", "faizan", "ghani", "habib", "hanif", "hashim", "inam", "jawad",
    "khuram", "lukman", "luqman", "mudassar", "nadeem", "owais", "pervaiz", "qasim", "rehmat", "sufyan",
    "tabish", "usama", "waqash", "yasser", "yasir", "zohaib", "zulqarnain", "alina", "anam", "anoosha",
    "aqsa", "areeba", "arooj", "asiya", "asma", "ayza", "bareera", "durre", "eman", "fizza", "hadia",
    "hoorain", "iman", "iram", "javeria", "khadija", "maheen", "maliha", "manahil", "minahil", "momina",
    "muniba", "muskan", "nayab", "neelam", "rabiya", "ramsha", "rimsha", "rohail", "romaisa", "rida",
    "sabahat", "safia", "sahar", "samra", "sanabil", "sarwat", "sehrish", "sheeza", "shiza", "sobia",
    "sundus", "tuba", "urwa", "wajiha", "yumna", "zarish", "zoya", "zubaida",

    # Indian / Hindu / Sanskrit / Telugu / Tamil / Kannada / Bengali Names
    "siddharth", "arjun", "rohit", "rahul", "aditya", "varun", "vikram", "anand", "karthik", "pranav",
    "suresh", "ramesh", "rajesh", "sunil", "deepak", "manish", "priya", "pooja", "ananya", "neha",
    "shreya", "divya", "sneha", "kavita", "swati", "aarav", "abhishek", "ajay", "alok", "amit",
    "anil", "ankit", "anupam", "aravind", "ashish", "ashwin", "avinash", "ayush", "bharat", "bhavesh",
    "chetan", "chirag", "darshan", "dev", "dhruv", "dinesh", "gaurav", "gautam", "girish", "harish",
    "harshit", "hemant", "ishaan", "jagdish", "jitendra", "karan", "keshav", "krishna", "kunal", "laksh",
    "madhav", "manoj", "mayank", "mithun", "mohit", "mukesh", "nakul", "naveen", "neeraj", "nikhil",
    "nitin", "pankaj", "parth", "pawan", "piyush", "pradeep", "prakash", "pramod", "prasad", "prashant",
    "praveen", "raghav", "raj", "rajan", "rajeev", "rakesh", "ram", "rishi", "ritesh", "ronit",
    "roshan", "sachin", "samar", "sandeep", "sanjay", "sanjeev", "santosh", "sarvesh", "satish", "saurabh",
    "shantanu", "shashank", "shekhar", "shiva", "shivam", "shyam", "sourabh", "subhash", "sudhir", "sumit",
    "suraj", "sushant", "tanmay", "tarun", "tejas", "uday", "ujjwal", "utkarsh", "vaibhav", "vance",
    "ved", "vidyut", "vijay", "vimal", "vinay", "vinod", "vipin", "vishal", "vishesh", "vishnu",
    "vivek", "yash", "yuvraj", "aadhya", "aarti", "aditi", "aishwarya", "akanksha", "amrita", "anjali",
    "ankita", "anushka", "aparna", "archana", "ashima", "bhavna", "deepa", "deepika", "dipti", "dishani",
    "ekta", "gayatri", "geeta", "ishita", "jyoti", "kamini", "kriti", "latika", "madhuri", "malini",
    "meera", "monika", "nandini", "nisha", "pallavi", "payal", "poonam", "prachi", "prerna", "radha",
    "ragini", "rakhi", "rashmi", "renu", "richa", "ritu", "riya", "roshni", "rupa", "sakshi", "sandhya",
    "shikha", "shilpa", "shobha", "shraddha", "shweta", "simran", "smriti", "sonal", "suchitra", "sugandha",
    "suman", "sunita", "surabhi", "tanu", "tanvi", "trisha", "upasana", "urvashi", "vaishali", "vandana",
    "varsha", "vidya",

    # -------------------------------------------------------------------------
    # 2. MIDDLE EASTERN & NORTH AFRICAN (MENA / Arabic, Turkish, Persian, Hebrew)
    # -------------------------------------------------------------------------
    "tarek", "ziyad", "zeyad", "youssef", "omar", "hisham", "bassam", "noura", "rania", "kareem",
    "karim", "fadi", "rami", "ziad", "wael", "mahmoud", "marwan", "nasser", "salah", "ghassan",
    "habib", "fouad", "haitham", "hazem", "khaled", "maher", "mounir", "nabil", "osama", "rafik",
    "safwan", "tamir", "walid", "yahia", "ziad", "asmaa", "basma", "dalia", "dina", "farida",
    "habiba", "hala", "hana", "heba", "layla", "leila", "maha", "mai", "malak", "mariam",
    "mona", "nada", "nour", "reem", "salma", "samar", "shaimaa", "yasmin", "yousra", "zeinab",
    # Turkish
    "emre", "burak", "mehmet", "can", "berk", "selin", "ezgi", "deniz", "kerem", "murat",
    "ahmet", "mustafa", "ali", "huseyin", "hasan", "ibrahim", "ismail", "osman", "halil", "suleyman",
    "ozan", "arda", "kaan", "mert", "baris", "tolga", "volkan", "onur", "koray", "serkan",
    "gokhan", "hakan", "ayse", "fatma", "emine", "hatice", "zeynep", "elif", "meryem", "gamze",
    "busra", "merve", "tugba", "ebru", "derya", "esra", "asli", "pinar", "damla", "sinem",
    # Persian / Iranian
    "kaveh", "arash", "reza", "nima", "sohrab", "parisa", "roya", "leila", "behzad", "babak",
    "dariush", "farhad", "hamid", "hossein", "kamran", "kourosh", "mani", "mehran", "milad", "omid",
    "payam", "pejman", "ramin", "saman", "sasan", "shahram", "siavash", "vahid", "azadeh", "bahar",
    "fereshteh", "marjan", "mina", "nasim", "niloufar", "sanaz", "sepideh", "shirin", "simin", "taraneh",
    # Hebrew / Israeli
    "ari", "avi", "dan", "doron", "elad", "erez", "eyal", "guy", "idan", "ilan",
    "itai", "lior", "matan", "noam", "omer", "oren", "roee", "ron", "shai", "tal",
    "tomer", "uri", "yael", "yaron", "yonatan", "yuval", "adi", "anat", "avital", "dana",
    "gal", "hila", "keren", "maya", "michal", "noa", "ronit", "shani", "shira", "tamar",

    # -------------------------------------------------------------------------
    # 3. WESTERN, ANGLOPHONE & CELTIC (US, UK, Canada, Australia, Ireland, NZ)
    # -------------------------------------------------------------------------
    "john", "david", "michael", "james", "robert", "william", "richard", "thomas", "charles", "daniel",
    "matthew", "anthony", "mark", "donald", "steven", "paul", "andrew", "joshua", "kenneth", "kevin",
    "brian", "george", "timothy", "ronald", "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas",
    "eric", "erik", "jonathan", "stephen", "larry", "justin", "scott", "brandon", "benjamin", "samuel",
    "gregory", "alexander", "frank", "patrick", "raymond", "jack", "dennis", "jerry", "tyler", "aaron",
    "jose", "adam", "nathan", "henry", "douglas", "zachary", "peter", "kyle", "walter", "ethan",
    "jeremy", "harold", "keith", "christian", "roger", "noah", "gerald", "carl", "terry", "sean",
    "austin", "arthur", "lawrence", "jesse", "dylan", "bryan", "joe", "jordan", "billy", "albert",
    "bruce", "willie", "gabriel", "logan", "alan", "juan", "wayne", "roy", "ralph", "randy",
    "eugene", "vincent", "russell", "louis", "philip", "bobby", "johnny", "bradley", "alex", "lucas",
    "oliver", "liam", "elijah", "mason", "sebastian", "aidan", "aiden", "owen", "jackson", "carter",
    "jayden", "wyatt", "julian", "grayson", "leo", "lincoln", "jaxon", "caleb", "nathaniel", "theodore",
    "hunter", "connor", "landon", "adrian", "asher", "cameron", "colton", "dominic", "ian", "cooper",
    "brayden", "easton", "colton", "jace", "angel", "declan", "weston", "evan", "miles", "max",
    "gavin", "chase", "cole", "tristan", "brantley", "harrison", "brody", "george", "grant", "elliot",
    "emily", "olivia", "emma", "charlotte", "amelia", "sophia", "isabella", "ava", "mia", "evelyn",
    "harper", "camila", "gianna", "abigail", "luna", "ella", "elizabeth", "sofia", "avery", "mila",
    "scarlett", "eleanor", "madison", "chloe", "layla", "penelope", "aria", "grace", "zoey", "nora",
    "riley", "lily", "aubrey", "violet", "aurora", "savannah", "audrey", "brooklyn", "bella", "claire",
    "skylar", "isla", "genesis", "naomi", "elena", "caroline", "eliana", "anna", "maya", "valentina",
    "ruby", "kennedy", "ivy", "ariana", "aimee", "allison", "samantha", "sarah", "autumn", "quinn",
    "eva", "piper", "hailey", "kaylee", "sadie", "clara", "delilah", "nevada", "hadley", "kinsley",
    "conor", "ciaran", "eoin", "liam", "ronan", "callum", "cormac", "finlay", "hamish", "rory",
    "caoimhe", "niamh", "siobhan", "ciara", "aoife", "aisling", "sorcha", "maeve", "grainne",

    # -------------------------------------------------------------------------
    # 4. CONTINENTAL EUROPEAN & SCANDINAVIAN (German, French, Italian, Nordic, Dutch)
    # -------------------------------------------------------------------------
    # French
    "jean", "pierre", "nicolas", "julien", "antoine", "sebastien", "mathieu", "guillaume", "alexandre", "romain",
    "thomas", "maxime", "florent", "benjamin", "vincent", "damien", "laurent", "christophe", "stephane", "olivier",
    "camille", "chloe", "mathilde", "manon", "marine", "lucie", "lea", "juliette", "claire", "marion",
    "celine", "aurelie", "emilie", "sarah", "laura", "audrey", "sophie", "charlotte", "elodie", "pauline",
    # German / Austrian / Swiss
    "stefan", "klaus", "lukas", "maximilian", "tobias", "florian", "felix", "jonas", "moritz", "niklas",
    "philipp", "simon", "jannik", "tim", "jan", "leon", "marcel", "sebastian", "daniel", "christian",
    "hannah", "lena", "lea", "laura", "anna", "sarah", "julia", "lisa", "marie", "katharina",
    "johanna", "sophie", "lara", "nele", "franziska", "melanie", "vanessa", "nadine", "claudia", "stefanie",
    # Nordic / Scandinavian (Swedish, Danish, Norwegian, Finnish)
    "linus", "lars", "henrik", "anders", "magnus", "freja", "astrid", "soren", "mikkel", "rasmus",
    "mads", "emil", "oliver", "valdemar", "lucas", "oscar", "gustav", "viktor", "elias", "axel",
    "antti", "juho", "matti", "aleksi", "eetu", "ville", "lauri", "jari", "mikko", "pekka",
    "milla", "emma", "alma", "ida", "maja", "alva", "ebba", "wilma", "klara", "saga",
    # Italian
    "marco", "matteo", "lorenzo", "alessandro", "federico", "francesco", "andrea", "gabriele", "mattia", "davide",
    "riccardo", "tommaso", "edoardo", "giuseppe", "antonio", "salvatore", "giovanni", "roberto", "stefano", "angelo",
    "giulia", "chiara", "francesca", "giorgia", "martina", "sara", "alice", "aurora", "sofia", "alessia",
    "elena", "federica", "valentina", "silvia", "elisa", "camilla", "greta", "beatrice", "ludovica", "marta",
    # Dutch / Flemish
    "daan", "sem", "lucas", "milan", "levi", "finn", "luuk", "bram", "mees", "lars",
    "thijs", "ruben", "tim", "stijn", "sven", "niels", "wouter", "jasper", "koen", "maarten",
    "sanne", "fleur", "lotte", "anouk", "femke", "noa", "lieke", "iris", "eva", "maaike",

    # -------------------------------------------------------------------------
    # 5. SLAVIC & EASTERN EUROPEAN (Russian, Ukrainian, Polish, Czech, Balkan, Romanian)
    # -------------------------------------------------------------------------
    "dmitry", "dmitri", "ivan", "alexei", "aleksei", "sergei", "sergey", "mikhail", "andrei", "artem",
    "maxim", "vladimir", "nikolai", "egor", "ilya", "kirill", "anton", "gleb", "pavel", "roman",
    "krzysztof", "piotr", "pawel", "tomasz", "michal", "jan", "jakub", "mateusz", "lukasz", "marcin",
    "stanislav", "vladislav", "rostislav", "bohdan", "yaroslav", "taras", "oleksiy", "vasyl", "yuriy", "volodymyr",
    "bogdan", "dragos", "radu", "marius", "cristian", "andrei", "florin", "alexandru", "stefan", "gabriel",
    "elena", "olga", "anna", "tatiana", "tatyana", "natalia", "natasha", "ekaterina", "irina", "svetlana",
    "yulia", "anastasia", "maria", "ksenia", "daria", "polina", "victoria", "viktoria", "valeria", "alisa",
    "agnieszka", "katarzyna", "magdalena", "joanna", "aleksandra", "monika", "ewa", "barbara", "dorota", "beata",
    "ioana", "andreea", "elena", "maria", "roxana", "raluca", "mihaela", "ana", "diana", "cristina",

    # -------------------------------------------------------------------------
    # 6. HISPANIC & LUSOPHONE (Spain, Latin America, Portugal, Brazil)
    # -------------------------------------------------------------------------
    "carlos", "alejandro", "javier", "diego", "manuel", "miguel", "jorge", "luis", "fernando", "roberto",
    "ricardo", "eduardo", "rafael", "mario", "sergio", "antonio", "pedro", "pablo", "ruben", "hector",
    "arturo", "victor", "raul", "oscar", "guillermo", "mateo", "santiago", "joaquin", "rodrigo", "andres",
    "ignacio", "emilio", "gonzalo", "facundo", "agustin", "nicolas", "matias", "lucas", "tomas", "felipe",
    "joao", "thiago", "matheus", "gabriel", "lucas", "guilherme", "gustavo", "felipe", "bernardo", "vinicius",
    "rodrigo", "bruno", "caio", "henrique", "diego", "leandro", "marcelo", "vitor", "leonardo", "renan",
    "maria", "ana", "laura", "carmen", "patricia", "isabel", "marta", "elena", "lucia", "valeria",
    "sofia", "isabella", "camila", "mariana", "daniela", "gabriela", "catalina", "valentina", "paula", "andrea",
    "beatriz", "larissa", "mariana", "carolina", "juliana", "leticia", "amanda", "fernanda", "bruna", "luana",

    # -------------------------------------------------------------------------
    # 7. EAST ASIAN & SOUTHEAST ASIAN (Chinese, Japanese, Korean, Vietnamese, Indonesian, Filipino)
    # -------------------------------------------------------------------------
    # Chinese Pinyin & Common Tech Names
    "chen", "wang", "zhang", "liu", "yang", "huang", "zhao", "wu", "zhou", "xu", "sun", "ma",
    "zhu", "hu", "guo", "he", "gao", "lin", "luo", "zheng", "liang", "xie", "song", "tang",
    "han", "feng", "deng", "cao", "peng", "zeng", "wei", "jun", "lei", "ming", "yan", "tao",
    "hui", "jie", "qiang", "gang", "yong", "ping", "chao", "bo", "bin", "xin", "yu", "hong",
    "ting", "fang", "ling", "jing", "li", "na", "min", "juan", "ying", "lan", "xia",
    # Japanese Romaji Names
    "kenji", "hiroshi", "takashi", "ryota", "daisuke", "yuki", "haruto", "sota", "yuto", "ren",
    "kaito", "asahi", "hayato", "shota", "kazuki", "tatsuya", "naoki", "kohei", "shin", "tomo",
    "sakura", "yui", "aoi", "hina", "rin", "miu", "yuna", "akari", "mei", "nanami",
    "ayaka", "kana", "rina", "haruka", "asuka", "misaki", "erika", "mai", "shiori", "nana",
    # Korean Romanized Names
    "minjun", "donghyun", "jihoon", "junho", "jinwoo", "minseo", "jisoo", "seojun", "hayeon", "doho",
    "jungwoo", "sungmin", "hyuk", "taeyang", "seungho", "jaehyun", "youngjae", "minsu", "dongwon", "sungjin",
    "jiwoo", "sohee", "chaewon", "eunji", "nayeon", "dahyun", "mina", "sana", "tzuyu", "jennie",
    # Vietnamese
    "nguyen", "tran", "minh", "duc", "hoang", "anh", "linh", "trang", "hieu", "nam",
    "thanh", "tuan", "hung", "son", "phuong", "hai", "thao", "mai", "huong", "ngoc",
    # Indonesian & Malay
    "budi", "agus", "siti", "dewi", "nur", "rizal", "hendra", "eko", "arif", "tri",
    "wahyu", "adi", "bayu", "fajar", "rizky", "dimas", "bagus", "ilham", "annisa", "putri",
    # Filipino
    "mark", "christian", "angelo", "jayson", "althea", "princess", "joshua", "kenneth", "justin", "aldrin",

    # -------------------------------------------------------------------------
    # 8. AFRICAN (Nigerian, Ghanaian, Kenyan, Ethiopian, South African, Senegalese)
    # -------------------------------------------------------------------------
    # Nigerian / Yoruba / Igbo / Hausa
    "chioma", "emeka", "babatunde", "oluwaseun", "adebayo", "chinedu", "ngozi", "amina", "chukwuma", "chidi",
    "ifeanyi", "obinna", "kelechi", "nnamdi", "ugochukwu", "olumide", "ayodele", "femi", "segun", "tunde",
    "ibrahim", "musa", "usman", "umar", "aliyu", "zainab", "fatima", "aisha", "hadiza", "hauwa",
    "amara", "chiamaka", "chinelo", "adaeze", "yetunde", "funmilayo", "folashade", "bukola", "tiwa", "simi",
    # Kenyan / East African / Swahili
    "juma", "mwangi", "kamau", "wanjiku", "ochieng", "achieng", "kipchoge", "otieno", "maina", "kariuki",
    "baraka", "amani", "faraji", "khamisi", "zuberi", "zawadi", "chiumbo", "tumaini", "furaha", "imani",
    # Ghanaian / Akan
    "kwame", "kofi", "kwesi", "abena", "akua", "nana", "kweku", "yaw", "afia", "yaa",
    "akosua", "adjwoa", "esi", "ama", "mensah", "owusu", "boateng", "asante", "appiah", "gyasi",
    # South African (Zulu, Xhosa, Sotho)
    "thabo", "sipho", "bongani", "nandi", "lerato", "tendai", "kagiso", "lesedi", "sibusiso", "lungelo",
    "mandla", "tapiwa", "simphiwe", "nomvula", "nokuthula", "zola", "ayanda", "busisiwe", "thandiwe", "lindiwe",
    # Ethiopian & Eritrean
    "abebe", "dawit", "yonas", "solomon", "bereket", "tariku", "haile", "tewodros", "samuel", "michael",
    "selam", "helen", "tigist", "bethlehem", "meron", "eden", "rahel", "senait", "marta", "almaz",

    # -------------------------------------------------------------------------
    # 9. NOTABLE TECH LEADERS, FOUNDERS & OPEN SOURCE LUMINARIES
    # -------------------------------------------------------------------------
    "satya", "sundar", "guido", "linus", "bill", "steve", "elon", "jeff", "sam", "sergey",
    "tim", "jensen", "danielle", "katie", "sarah", "laszlo", "horacio", "brendan", "bjarne",
    "vitalik", "ken", "dennis", "richard", "donald", "ada", "grace", "alan", "claude"
}

COMMON_SURNAMES: Set[str] = {
    # South Asian & Islamic Surnames
    "ashraf", "asif", "hameed", "ghaffar", "rashid", "khan", "ahmad", "ahmed", "ali", "malik", "sheikh",
    "syed", "shah", "javed", "siddiqui", "abbasi", "mirza", "baig", "mughal", "rehman", "rahman", "aziz",
    "khalid", "sultan", "alam", "raza", "munir", "zafar", "nawaz", "sarwar", "liaquat", "abid", "sajid",
    "majid", "zahid", "shahzad", "khurram", "shahbaz", "tanveer", "tanvir", "waheed", "wahid", "yousaf",
    "yusuf", "yaqoob", "ayub", "butt", "dar", "bhatti", "rana", "qureshi", "ansari", "chaudhry", "chaudhary",
    "bukhari", "kazmi", "gilani", "farooqi", "farooq", "faraz", "osmani", "nadella", "pichai", "altman",
    "sharma", "gupta", "singh", "kumar", "verma", "patel", "reddy", "joshi", "iyer", "nair", "rao", "kapoor",
    "agarwal", "bose", "das", "chatterjee", "banerjee", "ghosh", "mukherjee", "sen", "dutta", "choudhury",
    # Western, Anglo & European Surnames
    "smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis", "rodriguez", "martinez",
    "hernandez", "lopez", "gonzalez", "wilson", "anderson", "thomas", "taylor", "moore", "jackson", "martin",
    "lee", "perez", "thompson", "white", "harris", "sanchez", "clark", "ramirez", "lewis", "robinson",
    "walker", "young", "allen", "king", "wright", "scott", "torres", "nguyen", "hill", "flores", "green",
    "adams", "nelson", "baker", "hall", "rivera", "campbell", "mitchell", "carter", "roberts", "hansson",
    "rossum", "vanrossum", "levels", "torvalds", "gates", "blank", "graham", "wang", "collison", "monaghan",
    "bock", "gutierrez"
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
