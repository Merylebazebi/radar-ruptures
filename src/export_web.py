"""Export des alertes vers web/, lu par l'application Streamlit publiée en ligne.

L'app en ligne ne peut pas lire la base PostgreSQL de ton PC : on lui publie une copie
des données, sous forme de deux petits CSV versionnés dans GitHub. Les données ANSM
sont publiques, il n'y a rien de sensible.

    web/alertes.csv      les signalements ouverts du dernier scoring, avec leur risque
    web/historique.csv   par jour de scoring, le nombre de signalements par niveau de risque

Utilisation :
    python src/export_web.py
"""
import logging
import sys
from pathlib import Path

import pandas as pd

from chargement import LOG_DIR, connexion

RACINE = Path(__file__).resolve().parents[1]
WEB_DIR = RACINE / "web"

log = logging.getLogger("export_web")


def configurer_logs():
    LOG_DIR.mkdir(exist_ok=True)
    format_ = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(LOG_DIR / "export_web.log", encoding="utf-8")):
        handler.setFormatter(format_)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def main(argv=None):
    configurer_logs()
    WEB_DIR.mkdir(exist_ok=True)
    with connexion().connect() as cnx:
        alertes = pd.read_sql("""
            SELECT date_scoring, medicament, presentation, laboratoire, statut, est_mitm,
                   classe_atc, nb_alternatives_generiques, proba_rupture, niveau_risque, cis, cip13
            FROM marts.v_alertes
            WHERE est_dernier_scoring
            ORDER BY proba_rupture DESC""", cnx)
        historique = pd.read_sql("""
            SELECT date_scoring, statut, niveau_risque, count(*) AS nb_signalements
            FROM marts.v_alertes
            GROUP BY date_scoring, statut, niveau_risque
            ORDER BY date_scoring""", cnx)
    alertes.to_csv(WEB_DIR / "alertes.csv", index=False)
    historique.to_csv(WEB_DIR / "historique.csv", index=False)
    log.info("Export web : %d alertes, %d lignes d'historique", len(alertes), len(historique))
    return 0


if __name__ == "__main__":
    sys.exit(main())
