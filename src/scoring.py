"""Scoring quotidien : applique le modèle « champion » aux signalements ouverts.

Résultat dans marts.predictions, puis dans la vue marts.v_alertes lue par le tableau de bord :
une ligne par signalement ouvert et par jour de scoring, avec la probabilité d'être
une rupture. Pour une tension, une probabilité élevée signale un risque d'aggravation.

Idempotent : relancé le même jour, il remplace les prédictions du jour.

Utilisation :
    python src/scoring.py
"""
import logging
import sys
from datetime import date
from pathlib import Path

import mlflow
import pandas as pd
from sqlalchemy import text

from chargement import LOG_DIR, connexion
from entrainement import MLFLOW_URI, NOM_MODELE, TABLE, preparer

VUE_ALERTES = Path(__file__).resolve().parents[1] / "sql" / "service" / "v_alertes.sql"

log = logging.getLogger("scoring")


def configurer_logs():
    LOG_DIR.mkdir(exist_ok=True)
    format_ = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(LOG_DIR / "scoring.log", encoding="utf-8")):
        handler.setFormatter(format_)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def scorer(modele, df, version, jour):
    """Renvoie le tableau des prédictions, du plus risqué au moins risqué."""
    predictions = df[["id_produit", "cis", "cip13", "code_statut"]].copy()
    predictions["proba_rupture"] = modele.predict_proba(preparer(df))[:, 1].round(4)
    predictions["version_modele"] = str(version)
    predictions["date_scoring"] = jour
    return predictions.sort_values("proba_rupture", ascending=False)


def main(argv=None):
    configurer_logs()
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = mlflow.MlflowClient()
    try:
        version = client.get_model_version_by_alias(NOM_MODELE, "champion")
    except mlflow.exceptions.MlflowException:
        log.error("Aucun modèle « champion » dans le registre : lance d'abord python src/entrainement.py")
        return 1
    modele = mlflow.sklearn.load_model(f"models:/{NOM_MODELE}@champion")

    engine = connexion()
    with engine.connect() as cnx:
        df = pd.read_sql(f"SELECT * FROM {TABLE}", cnx)
    jour = date.today()
    predictions = scorer(modele, df, version.version, jour)

    with engine.begin() as cnx:
        cnx.execute(text("""
            CREATE TABLE IF NOT EXISTS marts.predictions (
                id_produit TEXT, cis TEXT, cip13 TEXT, code_statut INT,
                proba_rupture DOUBLE PRECISION, version_modele TEXT, date_scoring DATE
            )"""))
        cnx.execute(text("DELETE FROM marts.predictions WHERE date_scoring = :jour"), {"jour": jour})
        predictions.to_sql("predictions", cnx, schema="marts", if_exists="append", index=False)
        # La vue lue par Power BI dépend des marts, recréés par transformation.py : on la recrée ici.
        cnx.execute(text(VUE_ALERTES.read_text(encoding="utf-8")))

    tensions = predictions[predictions["code_statut"] == 2]
    log.info("%d signalements scorés avec %s version %s", len(predictions), NOM_MODELE, version.version)
    log.info("Tensions à surveiller (probabilité de rupture >= 0,5) : %d", int((tensions["proba_rupture"] >= 0.5).sum()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
