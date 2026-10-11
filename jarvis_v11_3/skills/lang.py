"""Which language is this text in? (en / uz / ru) — so Uzbek and Russian are read with the right voice."""
import re

UZ_WORDS = set("""va bilan uchun emas bu shu u men siz biz ular ham yoki agar qanday nima nega qachon qayerda bor
yo'q kerak bo'ladi bo'lsa bo'lgan qiling toping hisoblang yeching tenglama javob savol dars darslik ertaga bugun
kecha rahmat salom assalomu alaykum ustoz o'quvchi sinf maktab sonini soni necha nechta ta qilib keyin oldin
hamda lekin ammo chunki bilan barcha har qaysi mavzu misol masala test topshiriq soat daqiqa kun yil""".split())
EN_WORDS = set("""the a an is are was were be you your i me my we our he she they it this that these those to of
and or in on at for with from by good morning evening afternoon night please sir thanks thank hello hi yes no
not do does did have has will would can could should today tomorrow yesterday bring notebook lesson time""".split())
UZ_CYR_WORDS = {"ва", "билан", "учун", "эмас", "бу", "ҳам", "керак", "бўлади", "дарс", "савол", "жавоб", "рахмат",
                "салом", "устоз", "синф", "мактаб", "эртага", "бугун", "мен", "сиз", "биз", "улар", "нима", "қандай",
                "тайёр", "тайёрми", "келаман", "эртанги", "ассалому", "алайкум", "яхши", "йўқ", "бор"}
RU_WORDS = {"и", "в", "не", "на", "что", "это", "как", "но", "урок", "завтра", "привет", "часов", "я", "вы", "мы",
            "он", "она", "они", "здравствуйте", "спасибо", "будет", "есть", "для", "по", "с", "у", "к", "да", "нет"}
CYR2LAT = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i",
           "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
           "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "",
           "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h"}


def detect(text):
    sample = text[:3000]
    cyr = len(re.findall(r"[\u0400-\u04FF]", sample))
    lat = len(re.findall(r"[A-Za-z]", sample))
    if cyr > lat:
        words = re.findall(r"[\u0400-\u04FF]+", sample.lower())
        uz = 3 * len(re.findall(r"[ўқғҳ]", sample.lower())) + 2 * sum(w in UZ_CYR_WORDS for w in words) + \
            sum(1 for w in words if re.search(r"(?:ми|га|да|дан|ни|нинг|лар|моқ|япти|ман|сиз)$", w) and len(w) > 3)
        ru = 2 * sum(w in RU_WORDS for w in words) + 2 * len(re.findall(r"[ыщ]", sample.lower())) + \
            sum(1 for w in words if re.search(r"(?:ого|его|ать|ять|ить|ешь|ется|ция|ые|ий)$", w))
        return "uz" if uz > ru else "ru"
    words = re.findall(r"[a-zʻʼ'`‘’]+", sample.lower().replace("ʻ", "'").replace("’", "'").replace("‘", "'"))
    if not words:
        return "en"
    en = sum(1 for w in words if w in EN_WORDS or re.search(r"(?:ing|tion|ed|ly|'s|n't)$", w))
    uz = sum(1 for w in words if w in UZ_WORDS or re.search(r"(?:o'|g')", w) or
             (w not in EN_WORDS and re.search(r"(?:lar|larni|ning|dagi|ga|da|dan|ni|mi)$", w) and len(w) > 4))
    return "uz" if uz > en and uz / len(words) > 0.12 else "en"


def uz_latin(text):
    """Uzbek Cyrillic -> Latin (the Uzbek voice reads Latin best)."""
    out = []
    for ch in text:
        low = ch.lower()
        if low in CYR2LAT:
            r = CYR2LAT[low]
            out.append(r[:1].upper() + r[1:] if ch != low and r else r)
        else:
            out.append(ch)
    return "".join(out)
