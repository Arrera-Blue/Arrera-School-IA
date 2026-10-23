"""Les 12 images des codes des élèves (évolution E3) : un code est une suite de 4 images, 12⁴ = 20 736 codes.

Des dessins simples (SVG, generateur/interface/statique/codes/), sans police ni émoji : ils s'affichent de la même
façon sur tous les postes, et s'impriment. Chacun a un nom, lu à voix haute ou écrit sous l'image sur la carte.
"""

# (identifiant du fichier, nom affiché) — l'ordre compte : un code est une suite de rangs dans cette liste
IMAGES = (("soleil", "soleil"), ("lune", "lune"), ("etoile", "étoile"), ("coeur", "cœur"), ("arbre", "arbre"),
          ("maison", "maison"), ("fleur", "fleur"), ("poisson", "poisson"), ("nuage", "nuage"),
          ("bateau", "bateau"), ("pomme", "pomme"), ("champignon", "champignon"))
NOMBRE = len(IMAGES)


def decrire(code: tuple[int, ...]) -> list[dict]:
    """[{"image": "soleil", "nom": "soleil"}, …] : pour l'affichage d'une carte."""
    return [{"image": IMAGES[i][0], "nom": IMAGES[i][1]} for i in code]
