"""La liste des mots de Lexique 3.83, rangée dans l'application pour N4 du français (formes verbales inventées :
docs/Generateur-Procedural/controle-du-modele.md, décision 1 du 16/11) :

- `mots.txt.gz` : l'orthographe de chaque mot de Lexique (toutes les formes : « aurais », « arriva », « prendrions »),
  une par ligne, triées, compressées (324 Ko au lieu de 125 653 lignes dans le dépôt : choix de l'utilisateur du
  16/11) ; le même fichier à chaque construction (aucune date dans l'en-tête gzip) ;
- `LISEZMOI.md` : la source, la licence (CC BY-SA 4.0 : la liste dérivée garde la même licence), la date.

Usage : python -I construire_lexique.py <Lexique383.tsv> <generateur/moteur/validation/lexique>
(Lexique383.tsv : http://www.lexique.org, téléchargé à part.)"""
import csv
import gzip
import hashlib
import sys
from datetime import date
from pathlib import Path

source, dossier = Path(sys.argv[1]), Path(sys.argv[2])
mots = set()
with open(source, encoding="utf-8") as f:
    for ligne in csv.DictReader(f, delimiter="\t"):
        if ligne["ortho"]:
            mots.add(ligne["ortho"])
dossier.mkdir(parents=True, exist_ok=True)
with open(dossier / "mots.txt.gz", "wb") as brut, gzip.GzipFile(fileobj=brut, mode="wb", compresslevel=9, mtime=0,
                                                                filename="") as f:
    f.write(("\n".join(sorted(mots)) + "\n").encode("utf-8"))
empreinte = hashlib.sha256(source.read_bytes()).hexdigest()
(dossier / "LISEZMOI.md").write_text(f"""# La liste des mots de Lexique 3.83

Dérivée de **Lexique 3.83** (http://www.lexique.org), sous licence **Creative Commons Attribution - Partage dans les
mêmes conditions 4.0 International (CC BY-SA 4.0)** : https://creativecommons.org/licenses/by-sa/4.0/deed.fr.
**Ce fichier, dérivé, est sous la même licence.**

Lexique : New, B., Pallier, C., Ferrand, L. et Matos, R. (2001), « Une base de données lexicales du français
contemporain sur internet : LEXIQUE », *L'Année Psychologique*, 101, 447-462 ; New, B., Pallier, C., Brysbaert, M. et
Ferrand, L. (2004), « Lexique 2 : A New French Lexical Database », *Behavior Research Methods, Instruments, &
Computers*, 36(3), 516-524.

Ce qui en est gardé, rien d'autre : l'orthographe de chaque mot (`mots.txt.gz`, {len(mots)} mots, un par ligne,
compressés). Écrit le {date.today():%d/%m/%Y} par `scripts/lexique/construire_lexique.py`,
à partir de `Lexique383.tsv` (SHA-256 {empreinte}).

Usage : N4 du français reconnaît une forme verbale inventée par le modèle (« je parleons ») : après un pronom sujet,
un mot absent de `mots.txt.gz` (`generateur/moteur/validation/n4_francais.py` ;
docs/Generateur-Procedural/controle-du-modele.md).
""", encoding="utf-8")
print(f"{dossier} : {len(mots)} mots")
