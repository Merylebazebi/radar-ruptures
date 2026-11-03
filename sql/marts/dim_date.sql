-- Dimension date : un jour par ligne, de la plus ancienne à la plus lointaine date connue.
-- Certains signalements ont une date de début future (arrêt de commercialisation annoncé) :
-- max(date_debut) fait donc partie des bornes.
WITH bornes AS (
    SELECT
        least(min(date_debut), min(date_snapshot)) AS debut,
        greatest(max(date_snapshot), max(date_debut), max(date_remise_dispo), current_date) AS fin
    FROM staging.stg_ruptures
)
SELECT
    jour::date                              AS date,
    extract(year FROM jour)::int            AS annee,
    extract(quarter FROM jour)::int         AS trimestre,
    extract(month FROM jour)::int           AS mois,
    extract(week FROM jour)::int            AS semaine_iso,
    extract(isodow FROM jour)::int          AS jour_semaine,
    extract(isodow FROM jour) IN (6, 7)     AS est_week_end
FROM bornes, generate_series(bornes.debut, bornes.fin, interval '1 day') AS jour
