-- Dimension médicament (une ligne par CIS), d'après le dernier snapshot du référentiel :
-- spécialité + intérêt thérapeutique majeur (MITM, classe ATC) + groupe générique.
-- Les CIS en rupture absents du référentiel sont ajoutés, pour que chaque fait ait sa dimension.
WITH specialites AS (
    SELECT * FROM staging.stg_specialites
    WHERE date_snapshot = (SELECT max(date_snapshot) FROM staging.stg_specialites)
),
mitm AS (
    SELECT DISTINCT ON (cis) cis, code_atc, classe_atc_niveau1
    FROM staging.stg_mitm
    WHERE date_snapshot = (SELECT max(date_snapshot) FROM staging.stg_mitm)
    ORDER BY cis, code_atc
),
generiques AS (
    SELECT g.cis, g.id_groupe, g.libelle_groupe, g.est_princeps,
           count(*) OVER (PARTITION BY g.id_groupe) AS nb_specialites_groupe
    FROM staging.stg_generiques g
    WHERE g.date_snapshot = (SELECT max(date_snapshot) FROM staging.stg_generiques)
),
generiques_par_cis AS (
    SELECT DISTINCT ON (cis) * FROM generiques ORDER BY cis, id_groupe
),
cis_hors_referentiel AS (
    SELECT DISTINCT cis FROM staging.stg_ruptures
    EXCEPT
    SELECT cis FROM specialites
)
SELECT
    s.cis,
    s.denomination,
    s.forme_pharmaceutique,
    s.voies_administration,
    s.titulaires,
    s.etat_commercialisation,
    s.statut_amm,
    s.surveillance_renforcee,
    m.cis IS NOT NULL                      AS est_mitm,
    m.code_atc,
    m.classe_atc_niveau1,
    g.id_groupe                            AS id_groupe_generique,
    g.libelle_groupe                       AS libelle_groupe_generique,
    g.est_princeps,
    coalesce(g.nb_specialites_groupe, 1)   AS nb_specialites_groupe,
    TRUE                                   AS dans_referentiel
FROM specialites s
LEFT JOIN mitm m ON m.cis = s.cis
LEFT JOIN generiques_par_cis g ON g.cis = s.cis
UNION ALL
SELECT
    h.cis, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
    FALSE, NULL, NULL, NULL, NULL, NULL, 1,
    FALSE
FROM cis_hors_referentiel h
