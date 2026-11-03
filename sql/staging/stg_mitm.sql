-- Médicaments d'intérêt thérapeutique majeur (MITM) et leur classe ATC.
SELECT
    trim(cis)           AS cis,
    trim(code_atc)      AS code_atc,
    left(trim(code_atc), 1) AS classe_atc_niveau1,
    trim(denomination)  AS denomination,
    trim(titulaire)     AS titulaire,
    trim(exploitant)    AS exploitant,
    CASE WHEN date_mitm ~ '^\d{2}/\d{2}/\d{4}$' THEN to_date(date_mitm, 'DD/MM/YYYY') END AS date_mitm,
    date_snapshot
FROM raw.mitm
