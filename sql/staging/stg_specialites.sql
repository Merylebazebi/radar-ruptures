-- Spécialités (médicaments) de la BDPM, une ligne par CIS et par snapshot.
SELECT
    trim(cis)                     AS cis,
    trim(denomination)            AS denomination,
    trim(forme_pharmaceutique)    AS forme_pharmaceutique,
    trim(voies_administration)    AS voies_administration,
    trim(statut_amm)              AS statut_amm,
    trim(type_procedure_amm)      AS type_procedure_amm,
    trim(etat_commercialisation)  AS etat_commercialisation,
    CASE WHEN date_amm ~ '^\d{2}/\d{2}/\d{4}$' THEN to_date(date_amm, 'DD/MM/YYYY') END AS date_amm,
    trim(titulaires)              AS titulaires,
    lower(trim(surveillance_renforcee)) = 'oui' AS surveillance_renforcee,
    date_snapshot
FROM raw.specialites
