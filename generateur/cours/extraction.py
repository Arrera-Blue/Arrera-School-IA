"""Lire le texte d'un cours déposé (plan IA, IA2.2), sans risque.

Un fichier venu d'internet peut être piégé : un PDF construit pour faire tourner le lecteur sans fin ou remplir la
mémoire, une « bombe zip » (un DOCX de 10 Ko qui se décompresse en 10 Go), un XML qui appelle des entités externes,
du texte caché (blanc sur blanc) qui donne des consignes au modèle. D'où :
- le type vérifié **par le contenu** (les premiers octets), jamais par le nom ; PDF, DOCX, ODT et TXT seulement ;
- une taille et un nombre de pages limités ; pour DOCX et ODT, la taille **décompressée** contrôlée avant de lire ;
- le XML lu par defusedxml (ni entités externes, ni entités en cascade) ;
- rien n'est exécuté (les macros ne sont pas lues), aucun lien n'est suivi ;
- la lecture dans un **processus à part** (`extraire_a_part`), limité en temps de calcul et en durée, sans droit
  d'écrire un fichier, et limité en mémoire là où le système le permet (Linux ; macOS ignore cette limite) ;
- un PDF sans texte (scanné) est refusé : la reconnaissance de caractères est une perspective.

Le texte caché n'est pas repéré ici : il est lu comme le reste, et c'est la sécurité de la demande (moteur/securite.py)
qui refuse un cours contenant une consigne adressée au modèle (generateur/donnees/cours.py).

    python -m generateur.cours.extraction <nom> < fichier     (le processus à part : JSON sur la sortie)
"""

import io
import json
import logging
import re
import subprocess
import sys
import zipfile
from pathlib import Path

TAILLE_MAX = 20 * 1024 * 1024          # 20 Mo déposés
PAGES_MAX = 200
DECOMPRESSE_MAX = 60 * 1024 * 1024     # DOCX, ODT : 60 Mo une fois décompressés, tous fichiers compris
ENTREES_MAX = 2000                     # DOCX, ODT : fichiers dans l'archive
TEXTE_MIN = 40                         # caractères : en dessous, un PDF est sans doute scanné
DELAI_S = 30                           # durée de la lecture
CALCUL_S = 25                          # temps de calcul du processus à part
MEMOIRE = 1024 * 1024 * 1024           # 1 Go (Linux)

FORMATS = ("pdf", "docx", "odt", "txt")
RACINE = Path(__file__).resolve().parents[2]
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


class CoursIllisible(Exception):
    """Le fichier n'est pas gardé ; le message est pour l'enseignant."""


def type_du_fichier(contenu: bytes, nom: str = "") -> str:
    """Le format, d'après les premiers octets (le nom ne sert qu'à reconnaître un texte brut) ; ou CoursIllisible."""
    if contenu.startswith(b"%PDF-"):
        return "pdf"
    if contenu.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
                noms = set(archive.namelist())
                if "word/document.xml" in noms:
                    return "docx"
                if "content.xml" in noms and "mimetype" in noms and \
                        archive.read("mimetype").strip() == b"application/vnd.oasis.opendocument.text":
                    return "odt"
        except (zipfile.BadZipFile, KeyError, OSError):
            pass
        raise CoursIllisible("ce fichier est une archive, mais ni un document Word (DOCX) ni un document texte "
                             "OpenDocument (ODT)")
    if nom.lower().endswith((".txt", ".md")) and b"\x00" not in contenu[:4096]:
        return "txt"
    raise CoursIllisible("format non pris en charge : déposez un PDF (avec du texte), un DOCX, un ODT ou un TXT")


def _paragraphes(texte: str) -> list[str]:
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", texte) if p.strip()]


def _pdf(contenu: bytes) -> list[dict]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        lecteur = PdfReader(io.BytesIO(contenu), strict=False)
        if lecteur.is_encrypted and not lecteur.decrypt(""):
            raise CoursIllisible("ce PDF est protégé par un mot de passe")
        if len(lecteur.pages) > PAGES_MAX:
            raise CoursIllisible(f"ce PDF a {len(lecteur.pages)} pages : {PAGES_MAX} au plus")
        blocs = []
        for numero, page in enumerate(lecteur.pages, start=1):
            texte = page.extract_text() or ""
            blocs += [{"page": numero, "texte": p} for p in _paragraphes(texte.replace("\r", "\n"))
                      or ([texte.strip()] if texte.strip() else [])]
    except CoursIllisible:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, AttributeError, IndexError, RecursionError) as e:
        raise CoursIllisible(f"ce PDF n'a pas pu être lu ({type(e).__name__})") from None
    if sum(len(b["texte"]) for b in blocs) < TEXTE_MIN:
        raise CoursIllisible("ce PDF ne contient pas de texte (un document scanné ?) : la lecture des images n'est "
                             "pas prise en charge")
    return blocs


def _archive(contenu: bytes, document: str) -> bytes:
    """Le XML principal d'un DOCX ou d'un ODT, après avoir vérifié l'archive (bombe zip)."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
            infos = archive.infolist()
            if len(infos) > ENTREES_MAX:
                raise CoursIllisible(f"ce document contient {len(infos)} fichiers : {ENTREES_MAX} au plus")
            if sum(i.file_size for i in infos) > DECOMPRESSE_MAX:
                raise CoursIllisible("ce document est trop gros une fois décompressé (une « bombe zip » ?)")
            with archive.open(document) as f:
                xml = f.read(DECOMPRESSE_MAX + 1)  # la taille annoncée peut mentir : on ne lit pas au-delà
    except (zipfile.BadZipFile, KeyError, OSError, RuntimeError) as e:
        raise CoursIllisible(f"ce document n'a pas pu être ouvert ({type(e).__name__})") from None
    if len(xml) > DECOMPRESSE_MAX:
        raise CoursIllisible("ce document est trop gros une fois décompressé (une « bombe zip » ?)")
    return xml


def _xml(xml: bytes):
    from defusedxml import DefusedXmlException
    from defusedxml.ElementTree import ParseError, fromstring

    try:
        return fromstring(xml, forbid_dtd=True)
    except (DefusedXmlException, ParseError) as e:
        raise CoursIllisible(f"le texte de ce document est mal formé ou piégé ({type(e).__name__})") from None


def _docx(contenu: bytes) -> list[dict]:
    racine = _xml(_archive(contenu, "word/document.xml"))
    blocs = []
    for p in racine.iter(f"{W}p"):
        morceaux = []
        for e in p.iter():
            if e.tag == f"{W}t" and e.text:
                morceaux.append(e.text)
            elif e.tag in (f"{W}tab", f"{W}br", f"{W}cr"):
                morceaux.append(" ")
        texte = re.sub(r"\s+", " ", "".join(morceaux)).strip()
        if texte:
            blocs.append({"page": None, "texte": texte})
    return blocs


def _odt(contenu: bytes) -> list[dict]:
    racine = _xml(_archive(contenu, "content.xml"))
    blocs = []
    for e in racine.iter():
        if e.tag in (f"{TEXT}p", f"{TEXT}h"):
            texte = re.sub(r"\s+", " ", "".join(e.itertext())).strip()
            if texte:
                blocs.append({"page": None, "texte": texte})
    return blocs


def _txt(contenu: bytes) -> list[dict]:
    try:
        texte = contenu.decode("utf-8-sig")
    except UnicodeDecodeError:
        texte = contenu.decode("cp1252", errors="replace")
    return [{"page": None, "texte": p} for p in _paragraphes(texte)]


def extraire(contenu: bytes, nom: str = "") -> dict:
    """{"format": …, "pages": n (PDF) ou None, "blocs": [{"page", "texte"}]} ; ou CoursIllisible.
    À appeler dans le processus à part (`extraire_a_part`) : un fichier piégé n'y menace que ce processus."""
    if len(contenu) > TAILLE_MAX:
        raise CoursIllisible(f"fichier trop gros : {TAILLE_MAX // (1024 * 1024)} Mo au plus")
    format_ = type_du_fichier(contenu, nom)
    blocs = {"pdf": _pdf, "docx": _docx, "odt": _odt, "txt": _txt}[format_](contenu)
    if not blocs:
        raise CoursIllisible("aucun texte trouvé dans ce document")
    pages = max((b["page"] or 0) for b in blocs) or None
    return {"format": format_, "pages": pages, "blocs": blocs}


def _limiter() -> None:  # pragma: no cover (dans le processus à part)
    import resource

    for limite, valeur in ((resource.RLIMIT_CPU, CALCUL_S), (resource.RLIMIT_FSIZE, 0),
                           (resource.RLIMIT_AS, MEMOIRE), (resource.RLIMIT_CORE, 0)):
        try:
            resource.setrlimit(limite, (valeur, valeur))
        except (ValueError, OSError):  # macOS refuse RLIMIT_AS : le temps et l'écriture restent limités
            pass


def extraire_a_part(contenu: bytes, nom: str = "") -> dict:
    """`extraire`, dans un processus à part et limité ; CoursIllisible si la lecture échoue ou dépasse ses limites."""
    if len(contenu) > TAILLE_MAX:
        raise CoursIllisible(f"fichier trop gros : {TAILLE_MAX // (1024 * 1024)} Mo au plus")
    try:
        # -E -s : ni variables d'environnement Python, ni paquets de l'utilisateur ; le dépôt comme dossier courant
        fini = subprocess.run([sys.executable, "-E", "-s", "-m", "generateur.cours.extraction", nom[:200]],
                              input=contenu, capture_output=True, timeout=DELAI_S, preexec_fn=_limiter, check=False,
                              cwd=str(RACINE))
    except subprocess.TimeoutExpired:
        raise CoursIllisible(f"la lecture de ce fichier a pris plus de {DELAI_S} s") from None
    try:
        resultat = json.loads(fini.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CoursIllisible("la lecture de ce fichier a échoué (fichier piégé, ou trop lourd à lire)") from None
    if "erreur" in resultat:
        raise CoursIllisible(resultat["erreur"])
    return resultat


def main() -> int:  # pragma: no cover (le processus à part)
    nom = sys.argv[1] if len(sys.argv) > 1 else ""
    contenu = sys.stdin.buffer.read(TAILLE_MAX + 1)
    try:
        resultat = extraire(contenu, nom)
    except CoursIllisible as e:
        resultat = {"erreur": str(e)}
    except MemoryError:
        resultat = {"erreur": "ce fichier demande trop de mémoire à lire"}
    except Exception as e:  # un fichier piégé peut faire échouer le lecteur de n'importe quelle façon
        resultat = {"erreur": f"ce fichier n'a pas pu être lu ({type(e).__name__})"}
    sys.stdout.write(json.dumps(resultat, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
