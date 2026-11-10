"""Les tables de référence du générateur procédural (cycle 2, lot 0, étape 0.3) : ce qui se sait sans se calculer.

docs/Generateur-Procedural/cycle-2-cp-ce1-ce2.md §2 : en dehors des maths, la réponse d'une question ne se calcule
pas toujours (« Ils (chanter) au présent » → « chantent »). Elle se lit alors dans une table **écrite une fois, avec
ses sources, et relue par un humain** ; chaque question tirée est juste parce que la table l'est.

Une table : `donnees/<matière>/<nom>.yaml`

    description: Les formes conjuguées des verbes du programme.
    sources:                      # d'où viennent les lignes ; chaque ligne en cite une
      wikt: {nom: Wiktionnaire, url: "https://fr.wiktionary.org/", consulte: "2026-11-10", licence: CC BY-SA 4.0}
    proprietes:                   # les colonnes : « texte », « nombre », ou la liste des valeurs permises
      infinitif: texte
      temps: [present, futur, imparfait]
      personne: [je, tu, il, nous, vous, ils]
      forme: texte
    cle: [infinitif, temps, personne]    # jamais deux lignes pareilles sur ces colonnes
    lignes:
      - {infinitif: chanter, temps: present, personne: ils, forme: chantent, source: wikt}

**Le monde fermé** : chaque ligne donne **toutes** les propriétés (aucune vide), avec une valeur permise ; on ne
déduit jamais une réponse de l'absence d'une ligne. Une ligne peut porter une `note` (un commentaire).

**La relecture** : `python -m generateur.procedural.tables relire <matière>/<nom> --par "…"` la note dans
`donnees/relectures.yaml` (qui, quand, et l'empreinte de la table). Une table modifiée ensuite n'est plus relue.
**Un générateur dont une table n'est pas relue n'est jamais proposé** (procedural.candidats) : rien de ce qui n'a pas
été validé n'arrive à un élève. `python -m generateur.procedural.tables` : l'état de chaque table et ses défauts.
"""

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

DOSSIER = Path(__file__).parent / "donnees"
RELECTURES = "relectures.yaml"
TYPES = ("texte", "nombre")
CHAMPS_SOURCE = ("nom", "url", "consulte")
EN_PLUS = ("source", "note")  # les clés d'une ligne qui ne sont pas des propriétés


class TableInvalide(ValueError):
    """La table a des défauts : le message les donne tous."""


class TableInconnue(LookupError):
    pass


@dataclass(frozen=True)
class Table:
    matiere: str
    nom: str
    description: str
    sources: dict
    proprietes: dict
    cle: tuple
    lignes: tuple
    empreinte: str
    relecture: dict | None  # {"par", "le", "empreinte"} ; None : jamais relue

    @property
    def ident(self) -> str:
        return f"{self.matiere}/{self.nom}"

    @property
    def relue(self) -> bool:
        """Relue, et pas modifiée depuis."""
        return bool(self.relecture) and self.relecture.get("empreinte") == self.empreinte

    def filtrer(self, **criteres) -> list[dict]:
        """Les lignes qui ont ces valeurs : `filtrer(temps="present", personne="ils")`."""
        inconnues = [c for c in criteres if c not in self.proprietes]
        if inconnues:
            raise KeyError(f"{self.ident} : propriété inconnue {inconnues[0]!r}")
        return [ligne for ligne in self.lignes if all(ligne[c] == v for c, v in criteres.items())]

    def valeurs(self, propriete: str, **criteres) -> list:
        """Les valeurs distinctes d'une propriété (parmi les lignes qui ont ces valeurs), dans l'ordre de la table."""
        vues = []
        for ligne in self.filtrer(**criteres):
            if ligne[propriete] not in vues:
                vues.append(ligne[propriete])
        return vues

    def une(self, rng: random.Random, **criteres) -> dict:
        lignes = self.filtrer(**criteres)
        if not lignes:
            raise LookupError(f"{self.ident} : aucune ligne pour {criteres}")
        return rng.choice(lignes)


# --- lecture et contrôle --------------------------------------------------------------------------------

def _texte(valeur) -> str:
    return valeur.isoformat() if isinstance(valeur, date) else str(valeur)


def empreinte(donnees: dict) -> str:
    """L'empreinte de ce qui compte dans une table (sources, propriétés, clé, lignes) : la relecture la retient."""
    utile = {k: donnees.get(k) for k in ("sources", "proprietes", "cle", "lignes")}
    texte = json.dumps(utile, ensure_ascii=False, sort_keys=True, default=_texte)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def defauts(donnees: dict) -> list[str]:
    """Tout ce qui ne va pas dans une table (vide : rien)."""
    if not isinstance(donnees, dict):
        return ["la table n'est pas un dictionnaire YAML"]
    erreurs = []
    if not str(donnees.get("description") or "").strip():
        erreurs.append("description absente")
    sources = donnees.get("sources")
    if not isinstance(sources, dict) or not sources:
        erreurs.append("aucune source")
        sources = {}
    for ident, source in sources.items():
        manque = [c for c in CHAMPS_SOURCE if not str((source or {}).get(c) or "").strip()]
        if manque:
            erreurs.append(f"source {ident} : {', '.join(manque)} manquant")
    proprietes = donnees.get("proprietes")
    if not isinstance(proprietes, dict) or not proprietes:
        erreurs.append("aucune propriété")
        proprietes = {}
    for nom, sorte in proprietes.items():
        if nom in EN_PLUS:
            erreurs.append(f"propriété {nom!r} : nom réservé")
        if not (sorte in TYPES or (isinstance(sorte, list) and sorte and len(set(map(str, sorte))) == len(sorte))):
            erreurs.append(f"propriété {nom} : « texte », « nombre » ou une liste de valeurs distinctes")
    cle = donnees.get("cle")
    if not isinstance(cle, list) or not cle or any(c not in proprietes for c in cle):
        erreurs.append("clé absente, ou qui cite une propriété inconnue")
        cle = []
    lignes = donnees.get("lignes")
    if not isinstance(lignes, list) or not lignes:
        return erreurs + ["aucune ligne"]
    vues = {}
    for rang, ligne in enumerate(lignes, 1):
        if not isinstance(ligne, dict):
            erreurs.append(f"ligne {rang} : pas un dictionnaire")
            continue
        quoi = f"ligne {rang}"
        if inconnues := [k for k in ligne if k not in proprietes and k not in EN_PLUS]:
            erreurs.append(f"{quoi} : colonne inconnue {inconnues[0]!r}")
        for nom, sorte in proprietes.items():
            valeur = ligne.get(nom)
            if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
                erreurs.append(f"{quoi} : {nom} vide (monde fermé : chaque ligne donne toutes les propriétés)")
            elif sorte == "nombre" and (isinstance(valeur, bool) or not isinstance(valeur, int)):
                erreurs.append(f"{quoi} : {nom} n'est pas un nombre entier ({valeur!r})")
            elif sorte == "texte" and not isinstance(valeur, str):
                erreurs.append(f"{quoi} : {nom} n'est pas un texte ({valeur!r})")
            elif isinstance(sorte, list) and valeur not in sorte:
                erreurs.append(f"{quoi} : {nom} = {valeur!r}, hors des valeurs permises")
        if ligne.get("source") not in sources:
            erreurs.append(f"{quoi} : source {ligne.get('source')!r} inconnue")
        if cle:
            valeur_cle = tuple(_texte(ligne.get(c)) for c in cle)
            if valeur_cle in vues:
                erreurs.append(f"{quoi} : même clé que la ligne {vues[valeur_cle]} ({', '.join(valeur_cle)})")
            vues.setdefault(valeur_cle, rang)
    return erreurs


def _dossier(dossier: Path | None) -> Path:
    return Path(dossier) if dossier is not None else DOSSIER  # lu à l'appel : les tests le déplacent


def relectures(dossier: Path | None = None) -> dict:
    fichier = _dossier(dossier) / RELECTURES
    if not fichier.exists():
        return {}
    return yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}


def chemin(matiere: str, nom: str, dossier: Path | None = None) -> Path:
    if not all(p.replace("-", "").replace("_", "").isalnum() and p.islower() for p in (matiere, nom)):
        raise TableInconnue(f"table mal nommée : {matiere}/{nom}")
    return _dossier(dossier) / matiere / f"{nom}.yaml"


def charger(matiere: str, nom: str, dossier: Path | None = None) -> Table:
    """La table, contrôlée ; lève TableInconnue si elle n'existe pas, TableInvalide si elle a des défauts."""
    fichier = chemin(matiere, nom, dossier)
    if not fichier.exists():
        raise TableInconnue(f"table introuvable : {matiere}/{nom}")
    donnees = yaml.safe_load(fichier.read_text(encoding="utf-8"))
    if erreurs := defauts(donnees):
        raise TableInvalide(f"{matiere}/{nom} : " + " ; ".join(erreurs))
    relecture = relectures(dossier).get(f"{matiere}/{nom}")
    return Table(matiere, nom, donnees["description"].strip(), donnees["sources"], donnees["proprietes"],
                 tuple(donnees["cle"]), tuple(donnees["lignes"]), empreinte(donnees),
                 {k: _texte(v) for k, v in relecture.items()} if relecture else None)


def lister(dossier: Path | None = None) -> list[tuple[str, str]]:
    """(matière, nom) de chaque table, dans l'ordre."""
    return sorted((f.parent.name, f.stem) for f in _dossier(dossier).glob("*/*.yaml"))


def relues(matiere: str, noms, dossier: Path | None = None) -> bool:
    """Toutes ces tables existent, sont saines et relues depuis leur dernière modification."""
    try:
        return all(charger(matiere, nom, dossier).relue for nom in noms)
    except (TableInconnue, TableInvalide):
        return False


def relire(matiere: str, nom: str, par: str, dossier: Path | None = None, le: date | None = None) -> dict:
    """Note la relecture de la table telle qu'elle est (qui, quand, son empreinte)."""
    if not par.strip():
        raise ValueError("dire qui a relu la table (--par)")
    table = charger(matiere, nom, dossier)  # une table qui a des défauts ne se relit pas
    toutes = relectures(dossier)
    toutes[table.ident] = {"par": par.strip(), "le": (le or date.today()).isoformat(), "empreinte": table.empreinte}
    entete = ("# Les relectures des tables de référence (generateur/procedural/tables.py) : écrit par\n"
              "# « python -m generateur.procedural.tables relire » ; ne pas modifier à la main.\n")
    (_dossier(dossier) / RELECTURES).write_text(entete + yaml.safe_dump(toutes, allow_unicode=True, sort_keys=True),
                                            encoding="utf-8")
    return toutes[table.ident]


# --- la commande -----------------------------------------------------------------------------------------

def main(arguments: list[str] | None = None, dossier: Path | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m generateur.procedural.tables",
                                     description="Les tables de référence du générateur procédural : leur état, "
                                                 "leur relecture.")
    sous = parser.add_subparsers(dest="action")
    r = sous.add_parser("relire", help="noter qu'une table a été relue et validée, telle qu'elle est")
    r.add_argument("table", help="<matière>/<nom>, par exemple francais/conjugaisons")
    r.add_argument("--par", required=True, help="qui l'a relue")
    args = parser.parse_args(arguments)
    if args.action == "relire":
        matiere, _, nom = args.table.partition("/")
        try:
            note = relire(matiere, nom, args.par, dossier)
        except (TableInconnue, TableInvalide, ValueError) as e:
            print(f"Refusé : {e}", file=sys.stderr)
            return 1
        print(f"{args.table} : relue par {note['par']} le {note['le']}.")
        return 0
    tables = lister(dossier)
    if not tables:
        print("Aucune table de référence.")
        return 0
    code = 0
    for matiere, nom in tables:
        try:
            t = charger(matiere, nom, dossier)
        except TableInvalide as e:
            print(f"✗ {matiere}/{nom} : {e}")
            code = 1
            continue
        etat = (f"relue par {t.relecture['par']} le {t.relecture['le']}" if t.relue
                else "modifiée depuis sa relecture : à relire" if t.relecture else "pas encore relue")
        print(f"{'✓' if t.relue else '·'} {t.ident} : {len(t.lignes)} lignes, {etat}")
    return code


if __name__ == "__main__":
    sys.exit(main())
