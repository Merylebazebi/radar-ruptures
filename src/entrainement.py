"""Entraînement du modèle de ML, suivi dans MLflow.

Cible actuelle : pour un signalement ouvert, est-ce une rupture (1) ou une tension (0) ?
Le modèle apprend le profil des médicaments en rupture. Appliqué aux tensions, un score
élevé signale une tension qui « ressemble » à une rupture : c'est l'alerte pour l'acheteur.
Quand l'historique quotidien sera suffisant, on changera TABLE et CIBLE pour la cible
principale (passage de tension à rupture sous 30 jours), sans toucher au reste.

Trois modèles sont comparés en validation croisée. Chaque essai est un run MLflow
(paramètres, métriques, modèle). Le meilleur, selon la PR AUC, est enregistré dans le
registre de modèles MLflow avec l'alias « champion », que le scoring utilise ensuite.

Utilisation :
    python src/entrainement.py
    mlflow ui --backend-store-uri sqlite:///mlflow.db     # puis http://localhost:5000
"""
import logging
import sys
from pathlib import Path

import mlflow
import pandas as pd
from mlflow.models import infer_signature
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from chargement import LOG_DIR, connexion

RACINE = Path(__file__).resolve().parents[1]
MLFLOW_URI = f"sqlite:///{RACINE / 'mlflow.db'}"
EXPERIENCE = "radar-ruptures"
NOM_MODELE = "radar-ruptures-gravite"

TABLE = "marts.ml_signalements_ouverts"
CIBLE = "cible_rupture"
VARIABLES_NUMERIQUES = [
    "anciennete_jours", "nb_specialites_groupe", "nb_presentations",
    "taux_remboursement_max", "prix_moyen", "nb_signalements_titulaire",
]
VARIABLES_BOOLEENNES = [
    "concerne_toute_la_specialite", "dans_referentiel", "est_mitm", "est_princeps",
    "a_un_groupe_generique", "surveillance_renforcee", "agrement_collectivites",
]
VARIABLES_CATEGORIELLES = ["classe_atc_niveau1", "forme_simplifiee", "voie_principale"]
VARIABLES = VARIABLES_NUMERIQUES + VARIABLES_BOOLEENNES + VARIABLES_CATEGORIELLES

GRAINE = 42

log = logging.getLogger("entrainement")


def configurer_logs():
    LOG_DIR.mkdir(exist_ok=True)
    format_ = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(LOG_DIR / "entrainement.log", encoding="utf-8")):
        handler.setFormatter(format_)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def preparer(df):
    """Types attendus par scikit-learn : booléens en 0/1, numériques en float, catégories en texte."""
    X = df[VARIABLES].copy()
    X[VARIABLES_BOOLEENNES] = X[VARIABLES_BOOLEENNES].fillna(False).astype(int)
    X[VARIABLES_NUMERIQUES] = X[VARIABLES_NUMERIQUES].astype(float)
    X[VARIABLES_CATEGORIELLES] = X[VARIABLES_CATEGORIELLES].fillna("inconnue").astype(str)
    return X


def modeles_candidats():
    """Chaque modèle est un pipeline complet : la préparation fait partie du modèle enregistré."""
    def pretraitement(normaliser):
        numeriques = [("imputation", SimpleImputer(strategy="median"))]
        if normaliser:
            numeriques.append(("normalisation", StandardScaler()))
        return ColumnTransformer([
            ("num", Pipeline(numeriques), VARIABLES_NUMERIQUES),
            ("bool", "passthrough", VARIABLES_BOOLEENNES),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=5), VARIABLES_CATEGORIELLES),
        ])

    return {
        "regression_logistique": Pipeline([
            ("prep", pretraitement(normaliser=True)),
            ("modele", LogisticRegression(class_weight="balanced", max_iter=2000)),
        ]),
        "foret_aleatoire": Pipeline([
            ("prep", pretraitement(normaliser=False)),
            ("modele", RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced", random_state=GRAINE)),
        ]),
        "gradient_boosting": Pipeline([
            ("prep", pretraitement(normaliser=False)),
            ("modele", HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, class_weight="balanced", random_state=GRAINE)),
        ]),
    }


def evaluer(modele, X_test, y_test):
    proba = modele.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)
    return {
        "test_roc_auc": roc_auc_score(y_test, proba),
        "test_pr_auc": average_precision_score(y_test, proba),
        "test_precision": precision_score(y_test, pred, zero_division=0),
        "test_rappel": recall_score(y_test, pred, zero_division=0),
        "test_f1": f1_score(y_test, pred, zero_division=0),
    }


def entrainer(df):
    """Compare les modèles, trace chaque run dans MLflow et renvoie (nom, run_id) du meilleur."""
    X, y = preparer(df), df[CIBLE].astype(int)
    log.info("Jeu de données : %d signalements, dont %d ruptures (%.0f %%)", len(y), y.sum(), 100 * y.mean())
    if y.sum() < 10 or (1 - y).sum() < 10:
        raise ValueError("Moins de 10 exemples dans une des classes : entraînement impossible")

    # Jeu de test mis de côté (25 %), stratifié pour garder la même proportion de ruptures.
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, stratify=y, random_state=GRAINE)
    validation = StratifiedKFold(n_splits=5, shuffle=True, random_state=GRAINE)

    mlflow.set_experiment(EXPERIENCE)
    resultats = {}
    for nom, modele in modeles_candidats().items():
        with mlflow.start_run(run_name=nom) as run:
            cv = cross_validate(modele, X_train, y_train, cv=validation, scoring=["roc_auc", "average_precision"])
            modele.fit(X_train, y_train)
            metriques = {
                "cv_roc_auc": cv["test_roc_auc"].mean(),
                "cv_pr_auc": cv["test_average_precision"].mean(),
                "cv_pr_auc_ecart_type": cv["test_average_precision"].std(),
                **evaluer(modele, X_test, y_test),
            }
            mlflow.log_params({
                "modele": nom, "cible": CIBLE, "table": TABLE,
                "nb_lignes": len(y), "taux_positifs": round(float(y.mean()), 4),
                **{k: v for k, v in modele.named_steps["modele"].get_params().items() if isinstance(v, (int, float, str, bool)) or v is None},
            })
            mlflow.log_metrics(metriques)

            importance = permutation_importance(modele, X_test, y_test, scoring="average_precision", n_repeats=10, random_state=GRAINE)
            importances = pd.DataFrame({"variable": VARIABLES, "importance": importance.importances_mean}).sort_values("importance", ascending=False)
            mlflow.log_text(importances.to_csv(index=False), "importance_variables.csv")

            # cloudpickle : format de sauvegarde accepté par toutes les versions de MLflow
            mlflow.sklearn.log_model(
                modele, name="modele", serialization_format="cloudpickle",
                signature=infer_signature(X_train, modele.predict_proba(X_train)[:, 1]),
            )
            resultats[nom] = (metriques["cv_pr_auc"], run.info.run_id)
            log.info("%s : PR AUC (validation croisée) %.3f, ROC AUC test %.3f, rappel test %.2f",
                     nom, metriques["cv_pr_auc"], metriques["test_roc_auc"], metriques["test_rappel"])

    meilleur = max(resultats, key=lambda n: resultats[n][0])
    return meilleur, resultats[meilleur][1]


def enregistrer_champion(nom, run_id):
    """Ajoute le meilleur modèle au registre MLflow et lui donne l'alias « champion »."""
    version = mlflow.register_model(f"runs:/{run_id}/modele", NOM_MODELE)
    mlflow.MlflowClient().set_registered_model_alias(NOM_MODELE, "champion", version.version)
    log.info("Meilleur modèle : %s, enregistré comme %s version %s (alias champion)", nom, NOM_MODELE, version.version)


def main(argv=None):
    configurer_logs()
    mlflow.set_tracking_uri(MLFLOW_URI)
    with connexion().connect() as cnx:
        df = pd.read_sql(f"SELECT * FROM {TABLE}", cnx)
    nom, run_id = entrainer(df)
    enregistrer_champion(nom, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
