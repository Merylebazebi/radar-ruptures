"""Tests des transformations SQL et des tests qualité, sur une base de test.

Ignorés si TEST_DATABASE_URL n'est pas définie (voir test_chargement.py).
"""
import os
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

import chargement
import transformation

URL_TEST = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL_TEST, reason="TEST_DATABASE_URL non définie")

AUJOURD_HUI = date.today().isoformat()


def ligne_rupture(cis, statut="1", debut="01/10/2026", remise=""):
    libelle = {"1": "Rupture de stock", "2": "Tension d'approvisionnement"}.get(statut, "Autre")
    return f"{cis}\t\t{statut}\t{libelle}\t{debut}\t15/10/2026\t{remise}\thttps://ansm.sante.fr/x"


def ecrire(chemin, lignes):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("\n".join(lignes) + "\n", encoding="cp1252")


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base de test chargée avec un faux snapshot du jour : 150 ruptures + référentiels."""
    monkeypatch.setattr(chargement, "RACINE", tmp_path)
    monkeypatch.setattr(chargement, "RAW_DIR", tmp_path / "data" / "raw")
    monkeypatch.setattr(chargement, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(transformation, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setenv("DATABASE_URL", URL_TEST)
    engine = create_engine(URL_TEST)
    with engine.begin() as cnx:
        for schema in ("raw", "staging", "marts"):
            cnx.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))

    raw = tmp_path / "data" / "raw"
    jour = f"date={AUJOURD_HUI}"
    ruptures = [ligne_rupture(60000000 + i) for i in range(150)]
    ruptures.append(ligne_rupture(60000000))  # doublon exact
    ruptures.append(ligne_rupture(69999999, statut="2"))  # CIS absent du référentiel
    ruptures.append(ligne_rupture(60000003, statut="3", debut="01/06/2030"))  # début annoncé dans le futur
    ecrire(raw / "ruptures" / jour / "CIS_CIP_Dispo_Spec.txt", ruptures)
    ecrire(raw / "referentiel" / jour / "CIS_bdpm.txt",
           [f"{60000000 + i}\tDOLIPRANE 1000 mg, comprimé\tcomprimé\torale\tAutorisation active\tProcédure nationale\tCommercialisée\t01/01/2000\t\t\tOPELLA\tNon" for i in range(150)])
    ecrire(raw / "referentiel" / jour / "CIS_CIP_bdpm.txt", [
        "60000000\t3000001\tplaquette de 8\tPrésentation active\tDéclaration de commercialisation\t01/02/2001\t3400930000001\toui\t65%\t1,234,56\t1,236,58\t2,02\t",
        "60000001\t3000002\tplaquette de 16\tPrésentation active\tDéclaration de commercialisation\t01/02/2001\t3400930000002\tnon\t\t2,18\t3,20\t1,02\t",
    ])
    ecrire(raw / "referentiel" / jour / "CIS_GENER_bdpm.txt", ["1\tPARACETAMOL 1000 mg\t60000000\t0\t1"])
    ecrire(raw / "referentiel" / jour / "CIS_MITM.txt",
           ["60000000\tN02BE01\tDOLIPRANE 1000 mg, comprimé\tOPELLA\tOPELLA - PARIS\t05/10/2026\thttp://x"])
    assert chargement.main([]) == 0
    yield tmp_path, engine
    engine.dispose()


def requete(engine, sql):
    with engine.connect() as cnx:
        return cnx.execute(text(sql)).fetchall()


def test_construit_le_staging_et_les_tests_passent(base):
    _, engine = base
    assert transformation.main([]) == 0
    assert requete(engine, "SELECT count(*) FROM staging.stg_ruptures")[0][0] == 152  # doublon retiré


def test_convertit_dates_et_statuts(base):
    _, engine = base
    transformation.main([])
    statut, debut, toute_specialite = requete(engine, "SELECT statut, date_debut, concerne_toute_la_specialite FROM staging.stg_ruptures LIMIT 1")[0]
    assert statut == "rupture"
    assert debut == date(2026, 10, 1)
    assert toute_specialite is True  # CIP13 vide


def test_convertit_les_prix_au_format_bdpm(base):
    _, engine = base
    transformation.main([])
    prix = dict(requete(engine, "SELECT cip13, prix_sans_honoraires FROM staging.stg_presentations"))
    assert float(prix["3400930000001"]) == 1234.56
    assert float(prix["3400930000002"]) == 2.18


def test_un_statut_invalide_fait_echouer_les_tests(base):
    _, engine = base
    with engine.begin() as cnx:
        cnx.execute(text("UPDATE raw.ruptures SET code_statut = '9' WHERE cis = '60000001'"))
    assert transformation.main([]) == 1


def test_un_avertissement_ne_fait_pas_echouer(base):
    _, engine = base
    with engine.begin() as cnx:  # remise avant le début : simple avertissement
        cnx.execute(text("UPDATE raw.ruptures SET date_remise_dispo = '01/01/2020' WHERE cis = '60000001'"))
    assert transformation.main([]) == 0


def test_une_erreur_sql_laisse_la_base_intacte(base, monkeypatch):
    racine, engine = base
    transformation.main([])
    faux_sql = racine / "sql"
    (faux_sql / "staging").mkdir(parents=True)
    (faux_sql / "staging" / "a_ok.sql").write_text("SELECT 1 AS x")
    (faux_sql / "staging" / "b_casse.sql").write_text("SELECT * FROM table_inexistante")
    monkeypatch.setattr(transformation, "SQL_DIR", faux_sql)
    with pytest.raises(Exception):
        transformation.main([])
    tables = {t for (t,) in requete(engine, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'staging'")}
    assert "stg_ruptures" in tables and "a_ok" not in tables


def test_construit_le_modele_en_etoile(base):
    _, engine = base
    assert transformation.main([]) == 0
    assert requete(engine, "SELECT count(*) FROM marts.fct_signalements")[0][0] == 152
    assert requete(engine, "SELECT count(*) FROM marts.dim_statut")[0][0] == 4


def test_dim_medicament_enrichie_par_mitm_et_generiques(base):
    _, engine = base
    transformation.main([])
    est_mitm, atc, princeps = requete(engine, "SELECT est_mitm, code_atc, est_princeps FROM marts.dim_medicament WHERE cis = '60000000'")[0]
    assert est_mitm is True and atc == "N02BE01" and princeps is True


def test_cis_hors_referentiel_ajoute_a_la_dimension(base):
    _, engine = base
    transformation.main([])
    (dans_referentiel,) = requete(engine, "SELECT dans_referentiel FROM marts.dim_medicament WHERE cis = '69999999'")[0]
    assert dans_referentiel is False


def test_duree_et_statut_en_cours(base):
    _, engine = base
    transformation.main([])
    en_cours, duree = requete(engine, "SELECT est_en_cours, duree_jours FROM marts.fct_signalements WHERE cis = '60000002'")[0]
    assert en_cours is True  # pas de date de remise
    assert duree == (date.today() - date(2026, 10, 1)).days
