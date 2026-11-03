"""Tests de l'ingestion, sans réseau : le téléchargement est remplacé par un faux.

Lancer avec : pytest
"""
import json

import pytest
import requests

import ingestion

FAUX_FICHIER = ("60000001\t3400930000001\t1\tRupture de stock\t01/10/2026\t15/10/2026\t\thttps://ansm\n" * 5).encode("cp1252")


@pytest.fixture
def raw(tmp_path, monkeypatch):
    """Redirige la zone raw vers un dossier temporaire et compte les téléchargements."""
    monkeypatch.setattr(ingestion, "RAW_DIR", tmp_path)
    appels = []

    def faux_telecharger(nom):
        appels.append(nom)
        return FAUX_FICHIER

    monkeypatch.setattr(ingestion, "telecharger", faux_telecharger)
    return tmp_path, appels


def test_range_le_fichier_dans_le_dossier_du_jour(raw):
    dossier, _ = raw
    assert ingestion.collecter_zone("ruptures", "2026-11-01") == []
    cible = dossier / "ruptures" / "date=2026-11-01" / "CIS_CIP_Dispo_Spec.txt"
    assert cible.read_bytes() == FAUX_FICHIER  # copie brute, octet pour octet


def test_relance_le_meme_jour_ne_retelecharge_pas(raw):
    _, appels = raw
    ingestion.collecter_zone("ruptures", "2026-11-01")
    ingestion.collecter_zone("ruptures", "2026-11-01")
    assert appels == ["CIS_CIP_Dispo_Spec.txt"]


def test_force_retelecharge(raw):
    _, appels = raw
    ingestion.collecter_zone("ruptures", "2026-11-01")
    ingestion.collecter_zone("ruptures", "2026-11-01", force=True)
    assert len(appels) == 2


def test_metadata_contient_le_sha256(raw):
    dossier, _ = raw
    ingestion.collecter_zone("referentiel", "2026-11-01")
    metadata = json.loads((dossier / "referentiel" / "date=2026-11-01" / "_metadata.json").read_text())
    assert set(metadata) == set(ingestion.FICHIERS["referentiel"])
    assert len(metadata["CIS_bdpm.txt"]["sha256"]) == 64


def test_un_echec_n_arrete_pas_les_autres_fichiers(raw, monkeypatch):
    dossier, _ = raw

    def telecharger_partiel(nom):
        if nom == "CIS_MITM.txt":
            raise RuntimeError("serveur indisponible")
        return FAUX_FICHIER

    monkeypatch.setattr(ingestion, "telecharger", telecharger_partiel)
    assert ingestion.collecter_zone("referentiel", "2026-11-01") == ["CIS_MITM.txt"]
    assert (dossier / "referentiel" / "date=2026-11-01" / "CIS_bdpm.txt").exists()
    assert not (dossier / "referentiel" / "date=2026-11-01" / "CIS_MITM.txt").exists()


@pytest.mark.parametrize("contenu", [b"", b"<!DOCTYPE html><html>erreur 404</html>" * 10, b"pas de tabulation " * 20])
def test_refuse_un_contenu_qui_n_est_pas_un_fichier_bdpm(contenu):
    with pytest.raises(ValueError):
        ingestion.verifier_contenu("CIS_bdpm.txt", contenu)


def test_accepte_un_vrai_fichier():
    ingestion.verifier_contenu("CIS_CIP_Dispo_Spec.txt", FAUX_FICHIER)


def test_telecharger_reessaie_puis_abandonne(monkeypatch):
    essais = []

    def get_en_panne(*args, **kwargs):
        essais.append(1)
        raise requests.ConnectionError("pas de réseau")

    monkeypatch.setattr(ingestion.requests, "get", get_en_panne)
    monkeypatch.setattr(ingestion.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        ingestion.telecharger("CIS_bdpm.txt")
    assert len(essais) == ingestion.NB_ESSAIS
