"""Tableau de bord en ligne du Radar des ruptures (Streamlit Community Cloud).

Lit les CSV de web/, publiés chaque jour par scripts/publier.sh.
En local : streamlit run app/streamlit_app.py
"""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
CLASSES_ATC = {
    "A": "A · Digestif et métabolisme", "B": "B · Sang", "C": "C · Cardiovasculaire", "D": "D · Dermatologie",
    "G": "G · Génito-urinaire", "H": "H · Hormones", "J": "J · Anti-infectieux", "L": "L · Cancer et immunité",
    "M": "M · Muscles et squelette", "N": "N · Système nerveux", "P": "P · Antiparasitaires", "R": "R · Respiratoire",
    "S": "S · Organes sensoriels", "V": "V · Divers",
}
COULEURS_RISQUE = alt.Scale(domain=["1 - élevé", "2 - moyen", "3 - faible"], range=["#c0392b", "#e67e22", "#95a5a6"])

st.set_page_config(page_title="Radar des ruptures", page_icon="💊", layout="wide")


@st.cache_data(ttl=3600)
def charger():
    alertes = pd.read_csv(WEB_DIR / "alertes.csv", dtype={"cis": str, "cip13": str})
    historique = pd.read_csv(WEB_DIR / "historique.csv", parse_dates=["date_scoring"])
    alertes["classe_atc"] = alertes["classe_atc"].map(CLASSES_ATC).fillna("Non renseignée")
    return alertes, historique


alertes, historique = charger()
date_scoring = alertes["date_scoring"].max() if len(alertes) else "—"

st.title("Radar des ruptures de médicaments")
st.caption(
    f"Données ANSM (base de données publique des médicaments) au {date_scoring}. "
    "Le score estime, pour chaque signalement ouvert, la probabilité qu'il ait le profil d'une rupture de stock. "
    "Une tension avec un score élevé est un risque d'aggravation."
)

# Filtres
with st.sidebar:
    st.header("Filtres")
    niveaux = st.multiselect("Niveau de risque", sorted(alertes["niveau_risque"].unique()), default=sorted(alertes["niveau_risque"].unique()))
    statuts = st.multiselect("Statut", sorted(alertes["statut"].unique()), default=sorted(alertes["statut"].unique()))
    mitm_seul = st.toggle("Médicaments d'intérêt thérapeutique majeur uniquement")
    classes = st.multiselect("Classe ATC", sorted(alertes["classe_atc"].unique()))
    recherche = st.text_input("Rechercher un médicament ou un laboratoire")

vue = alertes[alertes["niveau_risque"].isin(niveaux) & alertes["statut"].isin(statuts)]
if mitm_seul:
    vue = vue[vue["est_mitm"]]
if classes:
    vue = vue[vue["classe_atc"].isin(classes)]
if recherche:
    masque = vue["medicament"].str.contains(recherche, case=False, na=False) | vue["laboratoire"].str.contains(recherche, case=False, na=False)
    vue = vue[masque]

# Indicateurs
tensions = alertes[alertes["statut"].str.startswith("Tension")]
risque_eleve = tensions[tensions["niveau_risque"] == "1 - élevé"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Signalements ouverts", len(alertes))
c2.metric("Tensions à risque élevé", len(risque_eleve))
c3.metric("dont médicaments d'intérêt majeur", int(risque_eleve["est_mitm"].sum()))
c4.metric("dont sans alternative générique", int((risque_eleve["nb_alternatives_generiques"] == 0).sum()))

# Tableau des alertes
st.subheader("Signalements à surveiller, du plus risqué au moins risqué")
st.dataframe(
    vue[["medicament", "presentation", "laboratoire", "statut", "est_mitm", "nb_alternatives_generiques", "proba_rupture", "niveau_risque"]],
    hide_index=True,
    use_container_width=True,
    column_config={
        "medicament": "Médicament",
        "presentation": "Présentation",
        "laboratoire": "Laboratoire",
        "statut": "Statut ANSM",
        "est_mitm": st.column_config.CheckboxColumn("Intérêt majeur"),
        "nb_alternatives_generiques": "Alternatives génériques",
        "proba_rupture": st.column_config.ProgressColumn("Risque", min_value=0, max_value=1, format="%.2f"),
        "niveau_risque": "Niveau",
    },
)

gauche, droite = st.columns(2)
with gauche:
    st.subheader("Par classe thérapeutique (ATC)")
    par_classe = vue.groupby(["classe_atc", "niveau_risque"]).size().reset_index(name="nb")
    st.altair_chart(
        alt.Chart(par_classe).mark_bar().encode(
            y=alt.Y("classe_atc:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
            x=alt.X("sum(nb):Q", title="Signalements"),
            color=alt.Color("niveau_risque:N", scale=COULEURS_RISQUE, title="Risque"),
            tooltip=["classe_atc", "niveau_risque", "nb"],
        ),
        use_container_width=True,
    )
with droite:
    st.subheader("Évolution des tensions à risque élevé")
    evolution = (historique[historique["statut"].str.startswith("Tension") & (historique["niveau_risque"] == "1 - élevé")]
                 .groupby("date_scoring", as_index=False)["nb_signalements"].sum())
    st.altair_chart(
        alt.Chart(evolution).mark_line(point=True, color="#c0392b").encode(
            x=alt.X("yearmonthdate(date_scoring):T", title=None, axis=alt.Axis(format="%d/%m", tickCount="day")),
            y=alt.Y("nb_signalements:Q", title="Tensions à risque élevé"),
            tooltip=["date_scoring", "nb_signalements"],
        ),
        use_container_width=True,
    )
    st.caption("La courbe s'allonge d'un point par jour de collecte.")

st.divider()
st.caption("Projet de certification Data Lead (Jedha) · Pipeline : Python → PostgreSQL (raw, staging, marts) → scikit-learn + MLflow → Streamlit")
