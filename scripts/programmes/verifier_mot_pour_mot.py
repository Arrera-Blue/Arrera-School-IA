import re, sys, unicodedata
from pathlib import Path
import yaml
textes, ref = Path(sys.argv[1]), Path(sys.argv[2])
SOURCES = {"maths-6e": "maths-c3.txt", "maths-5e": "maths-c4.txt", "francais-6e": "francais-c3.txt", "francais-5e": "francais-c4.txt"}
def plat(t):
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"=== page \d+ ===|education\.gouv\.fr BO n° \d+ \d+", " ", t)
    t = t.replace("𝑥", "x").replace("\n- ", " ").replace(" :\n- ", " : ")
    return re.sub(r"\s+", " ", t)
total = absents = 0
for nom, src in SOURCES.items():
    source = plat((textes / src).read_text(encoding="utf-8"))
    for theme in yaml.safe_load((ref / f"{nom}.yaml").read_text(encoding="utf-8"))["themes"]:
        for a in theme["attendus"]:
            total += 1
            l = a["libelle"]
            essais = [l, l.replace("a/b", "a b"), l.rstrip(".") , l.replace(" ; ", " ; - ").replace(" : ", " : - ")]
            if not any(re.sub(r"\s+", " ", e) in source for e in essais):
                absents += 1
                print("ABSENT", a["id"], l[:100])
print(f"{total} libellés, {absents} introuvables tels quels dans la source")
