"""N2 — l'instance respecte-t-elle le JSON Schema du type ?"""

from jsonschema import Draft202012Validator

from generateur.moteur.validation import ErreurValidation


def _ou(chemin) -> str:
    """questions/2/index_correct → « question 3, champ « index_correct » »."""
    morceaux = []
    parties = list(chemin)
    for i, partie in enumerate(parties):
        if isinstance(partie, int):
            parent = parties[i - 1] if i else ""
            nom = "question" if parent == "questions" else "proposition" if parent == "propositions" else "élément"
            morceaux[-1:] = [f"{nom} {partie + 1}"]
        else:
            morceaux.append(f"champ « {partie} »")
    return ", ".join(morceaux) or "racine"


def _message(err) -> str:
    v, attendu, valeur = err.validator, err.validator_value, err.instance
    ou = _ou(err.absolute_path)
    match v:
        case "required":
            manquants = [c for c in attendu if c not in valeur]
            return f"{ou} : champ obligatoire manquant « {', '.join(manquants)} »"
        case "additionalProperties":
            en_trop = sorted(set(valeur) - set(err.schema.get("properties", {})))
            return f"{ou} : champ non prévu « {', '.join(en_trop)} »"
        case "enum":
            return f"{ou} : « {valeur} » n'est pas une valeur permise ({', '.join(map(str, attendu))})"
        case "const":
            return f"{ou} : doit valoir « {attendu} », pas « {valeur} »"
        case "minimum" | "maximum":
            borne = "minimum" if v == "minimum" else "maximum"
            return f"{ou} : vaut {valeur}, {borne} autorisé {attendu}"
        case "minItems" | "maxItems":
            sens = "au moins" if v == "minItems" else "au plus"
            return f"{ou} : {len(valeur)} élément(s), il en faut {sens} {attendu}"
        case "minLength" | "maxLength":
            sens = "au moins" if v == "minLength" else "au plus"
            return f"{ou} : texte de {len(valeur)} caractère(s), il en faut {sens} {attendu}"
        case "type":
            return f"{ou} : type attendu « {attendu} », reçu « {type(valeur).__name__} »"
        case _:
            return f"{ou} : {err.message}"


def valider(instance: dict, schema: dict, meta_autorise: bool = False) -> None:
    erreurs = [_message(e) for e in sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda e: list(e.absolute_path))]
    # le schéma accepte « meta » pour la banque, mais le modèle n'a jamais le droit de le produire
    if not meta_autorise and "meta" in instance:
        erreurs.append("champ « meta » produit par le modèle : il est réservé au système")
    # ce que le schéma ne sait pas exprimer : l'index doit désigner une proposition qui existe
    if not erreurs:
        for i, q in enumerate(instance.get("questions", []), start=1):
            if "index_correct" in q and q["index_correct"] >= len(q.get("propositions", [])):
                erreurs.append(f"question {i}, champ « index_correct » : vaut {q['index_correct']}, "
                               f"mais il n'y a que {len(q['propositions'])} propositions")
    if erreurs:
        raise ErreurValidation("N2", erreurs)
