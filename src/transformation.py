"""Transformations SQL (staging, puis marts) et tests qualité, dans PostgreSQL.

C'est le "T" de l'ELT. Le principe reprend celui de dbt, pour pouvoir y passer en V2
sans réécrire le SQL :
    sql/<couche>/<modele>.sql   un SELECT par fichier ; le script crée la table
                                <couche>.<modele> à partir de ce SELECT
    sql/tests/<test>.sql        un SELECT qui renvoie les lignes en défaut :
                                0 ligne = test réussi

Chaque test indique sa sévérité dans sa première ligne :
    -- severite: erreur          le script échoue (code de sortie 1)
    -- severite: avertissement   le script signale, mais continue

Toutes les tables d'une couche sont reconstruites dans une seule transaction :
en cas d'erreur SQL, la base reste dans son état précédent.

Utilisation :
    python src/transformation.py                 # reconstruit les couches puis lance les tests
    python src/transformation.py --tests-seuls   # lance seulement les tests
"""
import argparse
import logging
import re
import sys
from pathlib import Path

from sqlalchemy import text

from chargement import LOG_DIR, connexion

RACINE = Path(__file__).resolve().parents[1]
SQL_DIR = RACINE / "sql"
COUCHES = ["staging", "marts"]  # dans l'ordre d'exécution

log = logging.getLogger("transformation")


def configurer_logs():
    LOG_DIR.mkdir(exist_ok=True)
    format_ = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(LOG_DIR / "transformation.log", encoding="utf-8")):
        handler.setFormatter(format_)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def construire_couche(engine, couche):
    """Recrée une table par fichier sql/<couche>/*.sql, dans l'ordre alphabétique."""
    fichiers = sorted((SQL_DIR / couche).glob("*.sql"))
    with engine.begin() as cnx:
        cnx.execute(text(f"CREATE SCHEMA IF NOT EXISTS {couche}"))
        for fichier in fichiers:
            modele = fichier.stem
            requete = fichier.read_text(encoding="utf-8").strip().rstrip(";")
            cnx.execute(text(f"DROP TABLE IF EXISTS {couche}.{modele} CASCADE"))
            cnx.execute(text(f"CREATE TABLE {couche}.{modele} AS\n{requete}"))
            nb = cnx.execute(text(f"SELECT count(*) FROM {couche}.{modele}")).scalar()
            log.info("%s.%s : %d lignes", couche, modele, nb)


def severite(requete):
    trouve = re.search(r"--\s*severite\s*:\s*(\w+)", requete)
    return trouve.group(1).lower() if trouve else "erreur"


def lancer_tests(engine):
    """Lance chaque test et renvoie la liste des tests en erreur (les avertissements ne comptent pas)."""
    echecs = []
    for fichier in sorted((SQL_DIR / "tests").glob("*.sql")):
        requete = fichier.read_text(encoding="utf-8").strip().rstrip(";")
        niveau = severite(requete)
        with engine.connect() as cnx:
            nb = cnx.execute(text(f"SELECT count(*) FROM (\n{requete}\n) AS t")).scalar()
        if nb == 0:
            log.info("test %s : OK", fichier.stem)
        elif niveau == "avertissement":
            log.warning("test %s : %d ligne(s) en défaut (avertissement)", fichier.stem, nb)
        else:
            log.error("test %s : %d ligne(s) en défaut", fichier.stem, nb)
            echecs.append(fichier.stem)
    return echecs


def main(argv=None):
    parser = argparse.ArgumentParser(description="Transformations SQL et tests qualité")
    parser.add_argument("--tests-seuls", action="store_true", help="ne pas reconstruire les tables, lancer seulement les tests")
    args = parser.parse_args(argv)

    configurer_logs()
    engine = connexion()
    if not args.tests_seuls:
        for couche in COUCHES:
            construire_couche(engine, couche)
    echecs = lancer_tests(engine)
    if echecs:
        log.error("Tests qualité : %d en échec (%s)", len(echecs), ", ".join(echecs))
        return 1
    log.info("Transformation et tests qualité terminés sans erreur")
    return 0


if __name__ == "__main__":
    sys.exit(main())
