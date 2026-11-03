-- Groupes génériques : relie chaque CIS à son groupe (princeps et génériques).
-- type_generique : 0 princeps, 1 générique, 2 génériques par complémentarité posologique, 4 substituable.
SELECT
    trim(id_groupe)        AS id_groupe,
    trim(libelle_groupe)   AS libelle_groupe,
    trim(cis)              AS cis,
    CASE WHEN type_generique ~ '^\d+$' THEN type_generique::int END AS type_generique,
    CASE WHEN type_generique ~ '^\d+$' THEN type_generique::int = 0 END AS est_princeps,
    CASE WHEN numero_tri ~ '^\d+$' THEN numero_tri::int END AS numero_tri,
    date_snapshot
FROM raw.generiques
