# AltaJobs — አሰሪና ሰራተኛን የሚያገናኝ ድህረ ገጽ

Flask + SQLite የተሰራ፣ 4 ቋንቋ (አማርኛ / English / Afaan Oromoo / ትግርኛ) የሚደግፍ፣
Facebook መሰል ፖስት/ላይክ/ኮመንት/ሼር ያለው፣ ደረጃ አሰጣጥ (rating) እና ሪፖርት ማድረጊያ ያለው፣
ወርሃዊ/አመታዊ ደንበኝነት (subscription) ስርዓት የተካተተበት መተግበሪያ።

## 🛠 VS Code ላይ እንዴት ማስኬድ እንደሚቻል

### 1. Python መጫኑን ያረጋግጡ (Python 3.9+)
```bash
python3 --version
```

### 2. ፕሮጀክቱን ይክፈቱ
VS Code ውስጥ ይህን ፎልደር (altajobs) ይክፈቱ (`File > Open Folder`)

### 3. Virtual environment ይፍጠሩ (አማራጭ ግን ይመከራል)
```bash
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
```

### 4. Dependencies ይጫኑ
```bash
pip install -r requirements.txt
```

### 5. መተግበሪያውን ያስኬዱ
```bash
python3 app.py
```
ከዚያ ብራውዘር ላይ ይህን ይክፈቱ፦ **http://localhost:5000**

የ SQLite ዳታቤዝ ፋይል (`altajobs.db`) ራሱ በራሱ ይፈጠራል፤ ምንም ተጨማሪ ማዋቀር አያስፈልግም።

---

## 📂 የፕሮጀክት አወቃቀር
```
altajobs/
├── app.py                 ← ዋናው Flask አፕ (routes, logic, DB)
├── translations.py        ← 4ቱ ቋንቋዎች መዝገበ ቃላት
├── requirements.txt
├── altajobs.db            ← (ራሱ በራሱ ይፈጠራል)
├── static/
│   ├── css/style.css      ← ንድፍ (mobile-friendly, አረንጓዴ ገጽታ)
│   └── uploads/           ← የተለጠፉ ፎቶዎች የሚቀመጡበት
└── templates/
    ├── base.html          ← የጋራ ገጽ (navbar, ቋንቋ መቀየሪያ)
    ├── login.html / register.html
    ├── feed.html          ← ዋና ዜና ማስፈንጠሪያ (Facebook-style)
    ├── post_detail.html   ← ነጠላ ፖስት + ኮመንቶች
    ├── profile.html       ← መገለጫ (ችሎታ/ልምድ/ደረጃ አሰጣጥ)
    ├── edit_profile.html
    ├── subscribe.html     ← የክፍያ እቅዶች
    └── admin.html         ← የአስተዳዳሪ ገጽ
```

## ✅ ያሉት ተግባራት

- **ምዝገባ/መግቢያ** — ሰራተኛ ወይም አሰሪ ሆኖ መመዝገብ ይቻላል
- **ፖስት ማድረግ** — ጽሑፍ + ፎቶ፣ 3 አይነት (አጠቃላይ / የስራ ማስታወቂያ / ችሎታ-ልምድ)
- **Like / Comment / Share / Save** — Facebook መሰል ግንኙነት + የተቀመጡ ስራዎች (Saved Jobs)
- **Dashboard Grid** — Saved Jobs (ይሰራል)፣ Groups / Events / Reels (በቅርቡ ይመጣል)
- **መገለጫ (Profile)** — ችሎታ፣ የስራ ልምድ፣ ስለ እኔ፣ ፎቶ
- **ደረጃ አሰጣጥ (Rating)** — አሰሪ ሰራተኛውን ከሰራ በኋላ በኮከብ (1-5) ይመዝናል
- **ሪፖርት ማድረጊያ + ማጽደቅ/ማገድ** — Admin ገጽ ላይ ሪፖርት ማየት፣ መፍታት፣ ተጠቃሚ ማገድ/እግድ ማንሳት
- **ደንበኝነት/ክፍያ** — 1 ወር ነጻ፣ ከዚያ 1,500 ብር/ወር ወይም 7,000 ብር/አመት
- **ዋሌት (Wallet)** — deposit/withdraw በቴሌብር `0960602675`፣ admin ማጽደቅ
- **Blue Tick (300 ብር/ወር) እና VIP (800 ብር/ወር)** — ከዋሌት ተቀናሽ፣ ✔️/👑 ምልክት
- **Animated Gifts** 🌹❤️⭐👑💎 — 30% ለመድረኩ (ለ admin) ተቆርጦ ቀሪው ለተቀባዩ
- **4 ቋንቋ** — አማርኛ/English/Afaan Oromoo/ትግርኛ
- **Premium Dark Theme** — Deep Slate (#1E293B) + Royal Blue (#1D9BF0)
- **ሞባይል ተስማሚ ንድፍ**

## 🏆 Monthly Business Challenge (NEW)

A judged (not random) monthly pitch competition:

- **Viral Gate** — users must follow 5 profiles + share their referral link with 3 friends before the entry payment button unlocks (`/challenge/invite`)
- **5 Entry Tiers** — 50 / 100 / 200 / 500 / 1000 ETB, paid from wallet, non-refundable, pooled per tier per month
- **Judged winner selection** — NOT a random draw. AI scores every pitch (`score_pitch_ai()`), admin adds a manual score, the entry with the highest combined score wins. A small engagement bonus (extra follows/referrals) can only nudge ties, never override pitch quality.
- **Platform fee** — 10% of the pool; the remaining 90% is the prize
- **Trust Protocol** — winner has 72 hours to submit guarantor ID info; admin approves → 50% released to wallet; winner then uploads proof-of-work photo; admin approves → remaining 50% released
- **Admin dashboard** — `/admin/challenges`: score pitches, select winners, approve guarantors, approve proof, mark forfeited if the winner misses the deadline

**AI scoring** — set `ANTHROPIC_API_KEY` as an environment variable to use real AI scoring via Claude. Without it, a simple heuristic (pitch length + business keywords) is used instead so the feature still works out of the box.

⚠️ Note: this was deliberately built as a **judged competition**, not a random-draw lottery. A random draw + paid entry + platform cut is legally a lottery in most jurisdictions (including Ethiopia, where it would fall under National Lottery Administration licensing) — the AI + admin scoring is what keeps this a skill-based contest instead.

## ☁️ Cloud Storage (Supabase) — አማራጭ

ፎቶዎች/avatar በነባሪ (default) በአካባቢያዊ ዲስክ (`static/uploads/`) ይቀመጣሉ — ምንም ተጨማሪ ማዋቀር ሳያስፈልግ ስራ ላይ ይውላል።

ፎቶዎችን ወደ ደመና (Supabase Storage) ማዛወር ከፈለጉ፦

1. [supabase.com](https://supabase.com) ላይ ነጻ ፕሮጀክት ይፍጠሩ
2. Storage ውስጥ `altajobs-uploads` የሚባል **public bucket** ይፍጠሩ
3. `pip install supabase --break-system-packages`
4. እነዚህን environment variable ያዘጋጁ (ወይም `.env` ፋይል ይጠቀሙ)፦
   ```bash
   export SUPABASE_URL="https://xxxx.supabase.co"
   export SUPABASE_KEY="your-service-role-or-anon-key"
   export SUPABASE_BUCKET="altajobs-uploads"   # አማራጭ፣ ነባሪው ይህ ነው
   ```
5. `python app.py` — ካስኬዱ በኋላ Terminal ላይ "✅ Supabase Storage connected" ብሎ ማየት አለብዎት

⚠️ ይህ ፎቶ/avatar ብቻ ነው የሚነካው። ዋናው ዳታቤዝ (ተጠቃሚ፣ ፖስት፣ ዋሌት ወዘተ) አሁንም SQLite ላይ ነው። ወደ ሙሉ Postgres/Supabase ዳታቤዝ ለመቀየር ትልቅ ፕሮጀክት ስለሆነ ለብቻው ማቀድ ይመከራል — ካስፈለገዎት በተለየ ደረጃ (phase) ልንሰራው እንችላለን።



## 👤 የመጀመሪያውን Admin እንዴት ማዘጋጀት ይቻላል
መጀመሪያ በተለመደው መንገድ ይመዝገቡ፣ ከዚያ በ terminal/DB browser (ለምሳሌ "DB Browser for SQLite") ውስጥ፦
```sql
UPDATE users SET is_admin = 1 WHERE username = 'የእርስዎ_ስም';
```
ይህን ካደረጉ በኋላ ዳግም ይግቡ፤ "Admin Panel" የሚለው ሊንክ በላይኛው ናቭ ባር ላይ ይታያል።

## ⚠️ ወደ production ከመሄድዎ በፊት
- `app.config["SECRET_KEY"]`ን በዘፈቀደ (random) ጠንካራ ቁልፍ ይቀይሩ
- ትክክለኛ የክፍያ API (ለምሳሌ Telebirr merchant API) ቢኖርዎት ወደ ራስ-ሰር ማረጋገጫ መቀየር ይመከራል
- HTTPS እና እውነተኛ ዶሜይን ማዋቀር ያስፈልጋል
- `debug=True`ን ወደ `False` ይቀይሩ

Enjoy! 🚀
