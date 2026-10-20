-- E1 : comptes enseignants, échecs de connexion, sessions, journal des accès (docs/etapes/etape-E1-securite.md).

CREATE TABLE enseignant (
    id INTEGER PRIMARY KEY,
    identifiant TEXT NOT NULL UNIQUE,              -- en minuscules (contrôlé par comptes.py)
    nom TEXT NOT NULL,                             -- nom affiché
    role TEXT NOT NULL CHECK (role IN ('admin', 'enseignant')),
    empreinte TEXT NOT NULL,                       -- scrypt$n$r$p$sel$cle : jamais le mot de passe
    doit_changer INTEGER NOT NULL DEFAULT 0,       -- 1 : mot de passe provisoire, à changer avant tout
    cree TEXT NOT NULL,
    mot_de_passe_change TEXT
);

-- les échecs se comptent par identifiant SAISI, qu'il existe ou non (on ne peut pas savoir si un compte
-- existe) ; la clé est une empreinte : un mot de passe tapé par erreur dans le champ identifiant n'est
-- jamais écrit en clair
CREATE TABLE echec_connexion (
    cle TEXT PRIMARY KEY,
    echecs INTEGER NOT NULL,
    dernier REAL NOT NULL,                         -- secondes depuis 1970 (time.time())
    verrou_jusqu_a REAL
);

-- le jeton de session n'est connu que du navigateur : la base garde son empreinte SHA-256
CREATE TABLE session (
    empreinte TEXT PRIMARY KEY,
    enseignant_id INTEGER NOT NULL REFERENCES enseignant (id) ON DELETE CASCADE,
    creee REAL NOT NULL,
    activite REAL NOT NULL
);
CREATE INDEX session_enseignant ON session (enseignant_id);

-- qui a fait quoi, quand ; ni mot de passe, ni jeton, ni code ; pas de clé étrangère : la trace d'un compte
-- reste après sa suppression ; effacé au bout de 6 mois (⚖6)
CREATE TABLE journal (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    enseignant_id INTEGER,
    identifiant TEXT,
    action TEXT NOT NULL,
    cible TEXT,
    detail TEXT
);
CREATE INDEX journal_date ON journal (date);
