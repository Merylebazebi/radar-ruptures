"""Chargement des fichiers de la zone raw dans le schéma `raw` de PostgreSQL.

C'est le "L" de l'ELT : les fichiers sont chargés presque tels quels,
toutes les colonnes en texte. Le nettoyage (dates, statuts, doublons) se fait
ensuite en SQL, dans les schémas staging et marts.

Ce que le script ajoute à chaque ligne :
    date_snapshot   la date du dossier date=AAAA-MM-JJ d'où vient la ligne
    fichier_source  le chemin du fichier, pour la traçabilité
    charge_le       l'heure du chargement

Idempotent : pour un fichier et une date, on supprime puis on réinsère dans la
même transaction. Relancer le script ne crée jamais de doublon.

Utilisation :
    python src/chargement.py                    # charge les dates pas encore en base
    python src/chargement.py --date 2026-11-03  # recharge une date précise
    python src/chargement.py --tout             # recharge toutes les dates

Connexion : variable DATABASE_URL, lue dans le fichier .env à la racine du projet.
"""
import argparse
import csv
import io
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

RACINE = Path(__file__).resolve().parents[1]
RAW_DIR = RACINE / "data" / "raw"
LOG_DIR = RACINE / "logs"

# Fichier BDPM -> (zone dans data/raw, table dans le schéma raw, colonnes dans l'ordre du fichier)
# Les fichiers n'ont pas d'en-tête : les noms viennent de la documentation BDPM
# "Contenu et format des fichiers téléchargeables" (v5).
SOURCES = {
    "CIS_CIP_Dispo_Spec.txt": ("ruptures", "ruptures", [
        "cis", "cip13", "code_statut", "libelle_statut",
        "date_debut", "date_maj", "date_remise_dispo", "lien_ansm",
    ]),
    "CIS_bdpm.txt": ("referentiel", "specialites", [
        "cis", "denomination", "forme_pharmaceutique", "voies_administration",
        "statut_amm", "type_procedure_amm", "etat_commercialisation", "date_amm",
        "statut_bdm", "numero_autorisation_europeenne", "titulaires", "surveillance_renforcee",
    ]),
    "CIS_CIP_bdpm.txt": ("referentiel", "presentations", [
        "cis", "cip7", "libelle_presentation", "statut_administratif",
        "etat_commercialisation", "date_declaration_commercialisation", "cip13",
        "agrement_collectivites", "taux_remboursement", "prix_sans_honoraires",
        "prix_avec_honoraires", "honoraires", "indications_remboursement",
    ]),
    "CIS_GENER_bdpm.txt": ("referentiel", "generiques", [
        "id_groupe", "libelle_groupe", "cis", "type_generique", "numero_tri",
    ]),
    "CIS_MITM.txt": ("referentiel", "mitm", [
        # 7 champs constatés sur le fichier réel (novembre 2026). Le sens de la
        # date n'est pas précisé dans les données : à confirmer dans la doc BDPM.
        "cis", "code_atc", "denomination", "titulaire", "exploitant", "date_mitm", "lien_bdpm",
    ]),
}

# Si une ligne a plus de champs que prévu, le surplus est gardé ici plutôt que perdu.
COLONNE_SURPLUS = "colonnes_en_trop"
COLONNES_TECHNIQUES = ["date_snapshot", "fichier_source", "charge_le"]

log = logging.getLogger("chargement")


def configurer_logs():
    LOG_DIR.mkdir(exist_ok=True)
    format_ = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(LOG_DIR / "chargement.log", encoding="utf-8")):
        handler.setFormatter(format_)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def connexion():
    load_dotenv(RACINE / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL manquante : crée un fichier .env (voir .env.exemple)")
    return create_engine(url)


def decoder(octets):
    """Les fichiers BDPM ont changé d'encodage selon les époques : on essaie UTF-8 puis Windows-1252."""
    for encodage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return octets.decode(encodage), encodage
        except UnicodeDecodeError:
            continue


def lire_fichier(chemin, colonnes):
    """Lit un fichier BDPM (tabulé, sans en-tête) et renvoie un DataFrame de textes.

    On découpe nous-mêmes avec le module csv plutôt qu'avec pd.read_csv :
    certaines lignes BDPM ont un champ de trop ou de moins, et read_csv
    planterait ou décalerait les colonnes. Ici, une ligne courte est complétée
    par des vides et le surplus d'une ligne longue part dans `colonnes_en_trop`.
    """
    texte, encodage = decoder(chemin.read_bytes())
    lignes = [l for l in csv.reader(io.StringIO(texte), delimiter="\t", quoting=csv.QUOTE_NONE) if any(c.strip() for c in l)]
    n = len(colonnes)
    trop_longues = sum(1 for l in lignes if len(l) > n and any(c.strip() for c in l[n:]))
    if trop_longues:
        log.warning("%s : %d ligne(s) avec plus de %d champs, surplus gardé dans %s", chemin.name, trop_longues, n, COLONNE_SURPLUS)

    donnees = []
    for l in lignes:
        valeurs = [c.strip() or None for c in l[:n]] + [None] * (n - len(l))
        surplus = "\t".join(l[n:]).strip() or None
        donnees.append(valeurs + [surplus])
    df = pd.DataFrame(donnees, columns=colonnes + [COLONNE_SURPLUS], dtype=object)
    log.info("%s : %d lignes lues (encodage %s)", chemin.name, len(df), encodage)
    return df


def colonnes_en_base(cnx, table):
    resultat = cnx.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = :table ORDER BY ordinal_position"
    ), {"table": table})
    return [c for (c,) in resultat]


def creer_tables(engine):
    """Crée les tables du schéma raw. Si les colonnes d'une table ne correspondent
    plus à SOURCES, la table est recréée : le raw se reconstruit toujours depuis
    les fichiers, et le chargement suivant recharge toutes ses dates."""
    with engine.begin() as cnx:
        cnx.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
        for _, table, colonnes in SOURCES.values():
            attendues = colonnes + [COLONNE_SURPLUS] + COLONNES_TECHNIQUES
            actuelles = colonnes_en_base(cnx, table)
            if actuelles and actuelles != attendues:
                log.warning("raw.%s : colonnes modifiées, table recréée (toutes les dates seront rechargées)", table)
                cnx.execute(text(f"DROP TABLE raw.{table}"))
            definition = ",\n    ".join(f"{c} TEXT" for c in colonnes + [COLONNE_SURPLUS])
            cnx.execute(text(f"""
                CREATE TABLE IF NOT EXISTS raw.{table} (
                    {definition},
                    date_snapshot DATE NOT NULL,
                    fichier_source TEXT NOT NULL,
                    charge_le TIMESTAMP NOT NULL
                )"""))
            cnx.execute(text(f"CREATE INDEX IF NOT EXISTS {table}_date_snapshot_idx ON raw.{table} (date_snapshot)"))


def snapshots_disponibles(zone, nom):
    """Dates des dossiers date=AAAA-MM-JJ qui contiennent ce fichier."""
    dates = []
    for dossier in sorted((RAW_DIR / zone).glob("date=*")):
        if (dossier / nom).exists():
            dates.append(date.fromisoformat(dossier.name.removeprefix("date=")))
    return dates


def snapshots_en_base(engine, table):
    with engine.connect() as cnx:
        return {d for (d,) in cnx.execute(text(f"SELECT DISTINCT date_snapshot FROM raw.{table}"))}


def charger_snapshot(engine, nom, jour):
    """Charge un fichier pour une date : supprime l'existant puis insère, dans une seule transaction."""
    zone, table, colonnes = SOURCES[nom]
    chemin = RAW_DIR / zone / f"date={jour.isoformat()}" / nom
    df = lire_fichier(chemin, colonnes)
    df["date_snapshot"] = jour
    df["fichier_source"] = str(chemin.relative_to(RACINE))
    df["charge_le"] = datetime.now()

    with engine.begin() as cnx:
        supprimees = cnx.execute(text(f"DELETE FROM raw.{table} WHERE date_snapshot = :jour"), {"jour": jour}).rowcount
        df.to_sql(table, cnx, schema="raw", if_exists="append", index=False, method="multi", chunksize=2000)
    detail = f", {supprimees} anciennes lignes remplacées" if supprimees else ""
    log.info("raw.%s : %d lignes chargées pour le %s%s", table, len(df), jour, detail)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Chargement de data/raw dans le schéma raw de PostgreSQL")
    groupe = parser.add_mutually_exclusive_group()
    groupe.add_argument("--date", type=date.fromisoformat, help="recharger une date précise (AAAA-MM-JJ)")
    groupe.add_argument("--tout", action="store_true", help="recharger toutes les dates")
    args = parser.parse_args(argv)

    configurer_logs()
    engine = connexion()
    creer_tables(engine)

    echecs = []
    for nom, (zone, table, _) in SOURCES.items():
        disponibles = snapshots_disponibles(zone, nom)
        if args.date:
            a_charger = [d for d in disponibles if d == args.date]
        elif args.tout:
            a_charger = disponibles
        else:
            deja = snapshots_en_base(engine, table)
            a_charger = [d for d in disponibles if d not in deja]
        if not a_charger:
            log.info("raw.%s : rien de nouveau à charger", table)
        for jour in a_charger:
            try:
                charger_snapshot(engine, nom, jour)
            except Exception as erreur:  # un fichier en échec ne bloque pas les autres
                log.error("raw.%s : échec du chargement du %s (%s)", table, jour, erreur)
                echecs.append(f"{nom} {jour}")

    if echecs:
        log.error("Chargement terminé avec %d échec(s) : %s", len(echecs), ", ".join(echecs))
        return 1
    log.info("Chargement terminé sans erreur")
    return 0


if __name__ == "__main__":
    sys.exit(main())
