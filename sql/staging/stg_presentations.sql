-- Présentations (boîtes, codes CIP) de la BDPM, une ligne par CIP13 et par snapshot.
-- Les prix BDPM utilisent la virgule à la fois pour les milliers et les décimales
-- (ex. "1,234,56") : on supprime toutes les virgules sauf la dernière.
SELECT
    trim(cis)                                  AS cis,
    trim(cip7)                                 AS cip7,
    trim(cip13)                                AS cip13,
    trim(libelle_presentation)                 AS libelle_presentation,
    trim(statut_administratif)                 AS statut_administratif,
    trim(etat_commercialisation)               AS etat_commercialisation,
    CASE WHEN date_declaration_commercialisation ~ '^\d{2}/\d{2}/\d{4}$'
         THEN to_date(date_declaration_commercialisation, 'DD/MM/YYYY') END AS date_declaration_commercialisation,
    lower(trim(agrement_collectivites)) = 'oui' AS agrement_collectivites,
    nullif(regexp_replace(taux_remboursement, '[^0-9]', '', 'g'), '')::int AS taux_remboursement_pct,
    nullif(replace(regexp_replace(regexp_replace(prix_sans_honoraires, '[^0-9,]', '', 'g'), ',(?=.*,)', '', 'g'), ',', '.'), '')::numeric AS prix_sans_honoraires,
    nullif(replace(regexp_replace(regexp_replace(prix_avec_honoraires, '[^0-9,]', '', 'g'), ',(?=.*,)', '', 'g'), ',', '.'), '')::numeric AS prix_avec_honoraires,
    date_snapshot
FROM raw.presentations
