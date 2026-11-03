"""Tests de l'entraînement et du scoring, sur des données simulées.

MLflow écrit dans un dossier temporaire : les tests ne touchent pas à ton mlflow.db.
"""
import os
from datetime import date

import mlflow
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

import entrainement
import scoring


def donnees_simulees(n=300, graine=0):
    """Signalements fictifs où les ruptures sont plus fréquentes chez les MITM sans générique."""
    rng = np.random.default_rng(graine)
    est_mitm = rng.random(n) < 0.4
    a_un_generique = rng.random(n) < 0.5
    proba = 0.05 + 0.5 * (est_mitm & ~a_un_generique)
    return pd.DataFrame({
        "id_produit": [f"6{i:07d}-TOUTES" for i in range(n)],
        "cis": [f"6{i:07d}" for i in range(n)],
        "cip13": None,
        "date_snapshot": date(2026, 11, 3),
        "code_statut": np.where(rng.random(n) < proba, 1, 2),
        "anciennete_jours": rng.integers(0, 900, n),
        "nb_specialites_groupe": rng.integers(1, 20, n),
        "nb_presentations": rng.integers(1, 6, n),
        "taux_remboursement_max": rng.choice([15, 30, 65, 100, None], n),
        "prix_moyen": rng.gamma(2, 10, n),
        "nb_signalements_titulaire": rng.integers(1, 30, n),
        "concerne_toute_la_specialite": rng.random(n) < 0.3,
        "dans_referentiel": True,
        "est_mitm": est_mitm,
        "est_princeps": rng.random(n) < 0.3,
        "a_un_groupe_generique": a_un_generique,
        "surveillance_renforcee": False,
        "agrement_collectivites": rng.random(n) < 0.6,
        "classe_atc_niveau1": rng.choice(list("ABCJLN"), n),
        "forme_simplifiee": rng.choice(["comprimé", "solution", "gélule"], n),
        "voie_principale": rng.choice(["orale", "intraveineuse"], n),
    }).assign(cible_rupture=lambda d: (d["code_statut"] == 1).astype(int))


@pytest.fixture
def mlflow_temporaire(tmp_path, monkeypatch):
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setattr(entrainement, "MLFLOW_URI", uri)
    monkeypatch.setattr(scoring, "MLFLOW_URI", uri)
    monkeypatch.chdir(tmp_path)  # les artefacts MLflow atterrissent dans le dossier temporaire
    mlflow.set_tracking_uri(uri)
    yield uri


def test_entraine_trois_modeles_et_garde_le_meilleur(mlflow_temporaire):
    nom, run_id = entrainement.entrainer(donnees_simulees())
    runs = mlflow.search_runs(experiment_names=[entrainement.EXPERIENCE])
    assert len(runs) == 3
    assert nom in entrainement.modeles_candidats()
    meilleur = runs.loc[runs["run_id"] == run_id, "metrics.cv_pr_auc"].iloc[0]
    assert meilleur == runs["metrics.cv_pr_auc"].max()


def test_le_modele_apprend_le_signal(mlflow_temporaire):
    _, run_id = entrainement.entrainer(donnees_simulees())
    auc = mlflow.get_run(run_id).data.metrics["test_roc_auc"]
    assert auc > 0.7  # bien mieux que le hasard (0,5) sur un signal simulé net


def test_refuse_un_jeu_trop_desequilibre(mlflow_temporaire):
    df = donnees_simulees().assign(cible_rupture=0)
    df.loc[:4, "cible_rupture"] = 1
    with pytest.raises(ValueError):
        entrainement.entrainer(df)


def test_champion_enregistre_puis_utilise_pour_scorer(mlflow_temporaire):
    df = donnees_simulees()
    nom, run_id = entrainement.entrainer(df)
    entrainement.enregistrer_champion(nom, run_id)
    modele = mlflow.sklearn.load_model(f"models:/{entrainement.NOM_MODELE}@champion")
    predictions = scoring.scorer(modele, df, "1", date(2026, 11, 3))
    assert len(predictions) == len(df)
    assert predictions["proba_rupture"].between(0, 1).all()
    assert predictions["proba_rupture"].is_monotonic_decreasing  # trié du plus risqué au moins risqué


URL_TEST = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not URL_TEST, reason="TEST_DATABASE_URL non définie")
def test_scoring_ecrit_les_predictions_sans_doublon(mlflow_temporaire, tmp_path, monkeypatch):
    import chargement
    monkeypatch.setattr(chargement, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(scoring, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setenv("DATABASE_URL", URL_TEST)
    df = donnees_simulees()
    nom, run_id = entrainement.entrainer(df)
    entrainement.enregistrer_champion(nom, run_id)

    engine = create_engine(URL_TEST)
    with engine.begin() as cnx:
        cnx.execute(text("DROP SCHEMA IF EXISTS marts CASCADE"))
        cnx.execute(text("CREATE SCHEMA marts"))
    df.to_sql("ml_signalements_ouverts", engine, schema="marts", index=False)

    assert scoring.main([]) == 0
    assert scoring.main([]) == 0  # relancé le même jour : remplace, ne duplique pas
    with engine.connect() as cnx:
        nb = cnx.execute(text("SELECT count(*) FROM marts.predictions")).scalar()
    assert nb == len(df)
    engine.dispose()
