-- Table de faits : un signalement ANSM tel qu'observé à une date de snapshot.
-- Grain : (produit, statut, date de début, date de snapshot).
-- Un produit est une présentation (CIP13) ou, si le CIP13 est vide, toute la spécialité (CIS).
SELECT
    r.cis || '-' || coalesce(r.cip13, 'TOUTES')     AS id_produit,
    r.cis,
    r.cip13,
    r.concerne_toute_la_specialite,
    r.code_statut,
    r.date_debut,
    r.date_maj,
    r.date_remise_dispo,
    r.date_snapshot,
    -- Toujours en cours à la date du snapshot ?
    (r.date_remise_dispo IS NULL OR r.date_remise_dispo > r.date_snapshot) AS est_en_cours,
    -- Durée : jusqu'à la remise à disposition si elle est connue, sinon jusqu'au snapshot
    (coalesce(least(r.date_remise_dispo, r.date_snapshot), r.date_snapshot) - r.date_debut) AS duree_jours,
    r.lien_ansm
FROM staging.stg_ruptures r
