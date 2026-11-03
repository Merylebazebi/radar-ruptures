"""Ingestion quotidienne des fichiers BDPM (ANSM) dans la zone raw.

Chaque exécution télécharge les fichiers du jour et les range ainsi :
    data/raw/ruptures/date=AAAA-MM-JJ/CIS_CIP_Dispo_Spec.txt
    data/raw/referentiel/date=AAAA-MM-JJ/CIS_bdpm.txt, ...
    data/raw/<zone>/date=AAAA-MM-JJ/_metadata.json   (url, taille, sha256, heure)

Les fichiers sont copiés tels quels, sans transformation : c'est la zone raw.
Le script est idempotent : relancé le même jour, il ne retélécharge pas
un fichier déjà présent (sauf avec --force).

Utilisation :
    python src/ingestion.py                 # toutes les zones
    python src/ingestion.py --zone ruptures # une seule zone
    python src/ingestion.py --force         # écrase les fichiers du jour

Code de sortie : 0 si tout est collecté, 1 si au moins un fichier a échoué
(cron et Airflow s'en servent pour détecter un échec).
"""
import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

BASE_URL = "https://base-donnees-publique.medicaments.gouv.fr/download/file/"

# Zone de la raw -> fichiers à collecter
FICHIERS = {
    "ruptures": ["CIS_CIP_Dispo_Spec.txt"],
    "referentiel": [
        "CIS_bdpm.txt",
        "CIS_CIP_bdpm.txt",
        "CIS_GENER_bdpm.txt",
        "CIS_MITM.txt",
    ],
}

RACINE = Path(__file__).resolve().parents[1]
RAW_DIR = RACINE / "data" / "raw"
LOG_DIR = RACINE / "logs"

NB_ESSAIS = 3
TIMEOUT_S = 60
TAILLE_MIN = 100  # en octets : en dessous, le fichier est considéré vide

log = logging.getLogger("ingestion")


def configurer_logs():
    LOG_DIR.mkdir(exist_ok=True)
    format_ = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(LOG_DIR / "ingestion.log", encoding="utf-8")):
        handler.setFormatter(format_)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def verifier_contenu(nom, contenu):
    """Refuse une réponse qui n'est pas un fichier BDPM (page d'erreur, fichier vide)."""
    if len(contenu) < TAILLE_MIN:
        raise ValueError(f"{nom} : fichier vide ou presque ({len(contenu)} octets)")
    debut = contenu.lstrip()[:15].lower()
    if debut.startswith(b"<!doctype") or debut.startswith(b"<html"):
        raise ValueError(f"{nom} : le serveur a renvoyé une page HTML au lieu du fichier")
    if b"\t" not in contenu[:2000]:
        raise ValueError(f"{nom} : aucune tabulation, ce n'est pas un fichier BDPM")


def telecharger(nom):
    """Télécharge un fichier et renvoie son contenu brut (octets). Réessaie en cas d'échec."""
    url = BASE_URL + nom
    for essai in range(1, NB_ESSAIS + 1):
        try:
            reponse = requests.get(url, timeout=TIMEOUT_S, headers={"User-Agent": "radar-ruptures (projet Jedha)"})
            reponse.raise_for_status()
            verifier_contenu(nom, reponse.content)
            return reponse.content
        except (requests.RequestException, ValueError) as erreur:
            log.warning("%s : essai %d/%d échoué (%s)", nom, essai, NB_ESSAIS, erreur)
            if essai < NB_ESSAIS:
                time.sleep(5 * essai)
    raise RuntimeError(f"{nom} : échec après {NB_ESSAIS} essais")


def ecrire_fichier(cible, contenu):
    """Écrit d'abord dans un fichier temporaire puis le renomme.

    Si le script s'arrête au milieu, on ne laisse jamais un fichier à moitié
    écrit sous le vrai nom (sinon la relance le croirait déjà collecté).
    """
    temporaire = cible.with_name(cible.name + ".tmp")
    temporaire.write_bytes(contenu)
    temporaire.replace(cible)


def ajouter_metadata(dossier, nom, contenu):
    chemin = dossier / "_metadata.json"
    metadata = json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {}
    metadata[nom] = {
        "url": BASE_URL + nom,
        "taille_octets": len(contenu),
        "sha256": hashlib.sha256(contenu).hexdigest(),
        "collecte_le": datetime.now().isoformat(timespec="seconds"),
    }
    ecrire_fichier(chemin, json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8"))


def collecter_zone(zone, jour, force=False):
    """Collecte les fichiers d'une zone pour un jour. Renvoie la liste des fichiers en échec."""
    dossier = RAW_DIR / zone / f"date={jour}"
    echecs = []
    for nom in FICHIERS[zone]:
        cible = dossier / nom
        if cible.exists() and not force:
            log.info("%s/%s : déjà collecté le %s, ignoré", zone, nom, jour)
            continue
        try:
            contenu = telecharger(nom)
        except RuntimeError as erreur:
            log.error(str(erreur))
            echecs.append(nom)
            continue
        dossier.mkdir(parents=True, exist_ok=True)
        ecrire_fichier(cible, contenu)
        ajouter_metadata(dossier, nom, contenu)
        log.info("%s/%s : enregistré (%d Ko)", zone, nom, len(contenu) // 1024)
    return echecs


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ingestion BDPM vers data/raw")
    parser.add_argument("--zone", choices=sorted(FICHIERS), help="ne collecter qu'une zone")
    parser.add_argument("--force", action="store_true", help="écraser les fichiers déjà collectés aujourd'hui")
    args = parser.parse_args(argv)

    configurer_logs()
    jour = date.today().isoformat()
    zones = [args.zone] if args.zone else list(FICHIERS)
    log.info("Début de l'ingestion du %s (zones : %s)", jour, ", ".join(zones))

    echecs = []
    for zone in zones:
        echecs += collecter_zone(zone, jour, force=args.force)

    if echecs:
        log.error("Ingestion terminée avec %d échec(s) : %s", len(echecs), ", ".join(echecs))
        return 1
    log.info("Ingestion terminée sans erreur")
    return 0


if __name__ == "__main__":
    sys.exit(main())
