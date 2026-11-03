"""Tests du chargement vers PostgreSQL.

Les tests de lecture tournent partout. Ceux qui écrivent en base ont besoin
d'une base de test vide, indiquée par la variable TEST_DATABASE_URL, sinon ils
sont ignorés. Exemple :
    TEST_DATABASE_URL=postgresql+psycopg2://radar:radar@localhost:5432/radar_test pytest
"""
import os
from datetime import date

import pytest
from sqlalchemy import create_engine, text

import chargement

COLONNES_RUPTURES = chargement.SOURCES["CIS_CIP_Dispo_Spec.txt"][2]
LIGNE = "60000001\t3400930000001\t1\tRupture de stock\t01/10/2026\t15/10/2026\t\thttps://ansm.sante.fr/x"


def ecrire(chemin, texte, encodage="utf-8"):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(texte.encode(encodage))
    return chemin


# --- Lecture des fichiers (sans base) -------------------------------------

def test_lit_les_colonnes_dans_l_ordre(tmp_path):
    df = chargement.lire_fichier(ecrire(tmp_path / "f.txt", LIGNE + "\n"), COLONNES_RUPTURES)
    assert df.loc[0, "cis"] == "60000001"
    assert df.loc[0, "code_statut"] == "1"
    assert df.loc[0, "date_remise_dispo"] is None  # champ vide -> NULL


def test_garde_les_zeros_en_tete_des_codes(tmp_path):
    df = chargement.lire_fichier(ecrire(tmp_path / "f.txt", LIGNE.replace("60000001", "00012345") + "\n"), COLONNES_RUPTURES)
    assert df.loc[0, "cis"] == "00012345"


def test_lit_un_fichier_windows_1252(tmp_path):
    df = chargement.lire_fichier(ecrire(tmp_path / "f.txt", LIGNE.replace("Rupture", "Arrêt") + "\n", "cp1252"), COLONNES_RUPTURES)
    assert df.loc[0, "libelle_statut"] == "Arrêt de stock"


def test_ligne_courte_completee_et_ligne_longue_conservee(tmp_path):
    texte = "60000001\t\t2\tTension\n" + LIGNE + "\tchamp inattendu\n"
    df = chargement.lire_fichier(ecrire(tmp_path / "f.txt", texte), COLONNES_RUPTURES)
    assert len(df) == 2
    assert df.loc[0, "lien_ansm"] is None
    assert df.loc[1, chargement.COLONNE_SURPLUS] == "champ inattendu"


def test_ignore_les_lignes_vides(tmp_path):
    df = chargement.lire_fichier(ecrire(tmp_path / "f.txt", LIGNE + "\n\n" + LIGNE + "\n"), COLONNES_RUPTURES)
    assert len(df) == 2


# --- Chargement en base -----------------------------------------------------

URL_TEST = os.environ.get("TEST_DATABASE_URL")
avec_base = pytest.mark.skipif(not URL_TEST, reason="TEST_DATABASE_URL non définie")


@pytest.fixture
def projet(tmp_path, monkeypatch):
    """Un faux projet : data/raw avec deux jours de ruptures, et une base de test vide."""
    monkeypatch.setattr(chargement, "RACINE", tmp_path)
    monkeypatch.setattr(chargement, "RAW_DIR", tmp_path / "data" / "raw")
    monkeypatch.setattr(chargement, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setenv("DATABASE_URL", URL_TEST or "")
    raw = tmp_path / "data" / "raw" / "ruptures"
    ecrire(raw / "date=2026-11-02" / "CIS_CIP_Dispo_Spec.txt", LIGNE + "\n")
    ecrire(raw / "date=2026-11-03" / "CIS_CIP_Dispo_Spec.txt", LIGNE + "\n" + LIGNE.replace("60000001", "60000002") + "\n")
    engine = create_engine(URL_TEST)
    with engine.begin() as cnx:
        cnx.execute(text("DROP SCHEMA IF EXISTS raw CASCADE"))
    yield tmp_path, engine
    engine.dispose()


def compter(engine, where="TRUE"):
    with engine.connect() as cnx:
        return cnx.execute(text(f"SELECT count(*) FROM raw.ruptures WHERE {where}")).scalar()


@avec_base
def test_charge_chaque_date_avec_sa_date_snapshot(projet):
    _, engine = projet
    assert chargement.main([]) == 0
    assert compter(engine, "date_snapshot = '2026-11-02'") == 1
    assert compter(engine, "date_snapshot = '2026-11-03'") == 2


@avec_base
def test_relancer_ne_cree_pas_de_doublon(projet):
    _, engine = projet
    chargement.main([])
    chargement.main([])
    chargement.main(["--tout"])
    assert compter(engine) == 3


@avec_base
def test_recharger_une_date_remplace_ses_lignes(projet):
    racine, engine = projet
    chargement.main([])
    ecrire(racine / "data/raw/ruptures/date=2026-11-03/CIS_CIP_Dispo_Spec.txt", LIGNE + "\n")
    chargement.main(["--date", "2026-11-03"])
    assert compter(engine, "date_snapshot = '2026-11-03'") == 1
    assert compter(engine, "date_snapshot = '2026-11-02'") == 1  # les autres dates ne bougent pas


@avec_base
def test_trace_le_fichier_source(projet):
    _, engine = projet
    chargement.main([])
    with engine.connect() as cnx:
        source = cnx.execute(text("SELECT fichier_source FROM raw.ruptures WHERE date_snapshot = '2026-11-02'")).scalar()
    assert source == "data/raw/ruptures/date=2026-11-02/CIS_CIP_Dispo_Spec.txt"
