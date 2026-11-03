-- Ruptures et tensions déclarées à l'ANSM, une ligne par signalement et par jour de snapshot.
-- Dates converties, statut lisible, doublons exacts retirés.
WITH source AS (
    SELECT
        trim(cis)                                   AS cis,
        nullif(trim(cip13), '')                     AS cip13,
        CASE WHEN code_statut ~ '^\d+$' THEN code_statut::int END AS code_statut,
        trim(libelle_statut)                        AS libelle_statut,
        CASE WHEN date_debut ~ '^\d{2}/\d{2}/\d{4}$' THEN to_date(date_debut, 'DD/MM/YYYY') END               AS date_debut,
        CASE WHEN date_maj ~ '^\d{2}/\d{2}/\d{4}$' THEN to_date(date_maj, 'DD/MM/YYYY') END                   AS date_maj,
        CASE WHEN date_remise_dispo ~ '^\d{2}/\d{2}/\d{4}$' THEN to_date(date_remise_dispo, 'DD/MM/YYYY') END AS date_remise_dispo,
        lien_ansm,
        date_snapshot
    FROM raw.ruptures
),
dedoublonne AS (
    SELECT *,
        row_number() OVER (
            PARTITION BY date_snapshot, cis, coalesce(cip13, ''), code_statut, date_debut
            ORDER BY date_maj DESC NULLS LAST
        ) AS rang
    FROM source
)
SELECT
    cis,
    cip13,
    cip13 IS NULL AS concerne_toute_la_specialite,
    code_statut,
    CASE code_statut
        WHEN 1 THEN 'rupture'
        WHEN 2 THEN 'tension'
        WHEN 3 THEN 'arret_commercialisation'
        WHEN 4 THEN 'remise_a_disposition'
    END AS statut,
    libelle_statut,
    date_debut,
    date_maj,
    date_remise_dispo,
    lien_ansm,
    date_snapshot
FROM dedoublonne
WHERE rang = 1
