-- Dimension présentation (une ligne par CIP13, c'est-à-dire par boîte), d'après le dernier snapshot.
SELECT
    cip13,
    cip7,
    cis,
    libelle_presentation,
    etat_commercialisation,
    agrement_collectivites,
    taux_remboursement_pct,
    prix_avec_honoraires
FROM staging.stg_presentations
WHERE date_snapshot = (SELECT max(date_snapshot) FROM staging.stg_presentations)
