-- Dimension statut ANSM, avec un niveau de gravité pour trier et colorer les tableaux de bord.
SELECT * FROM (VALUES
    (1, 'rupture',                 'Rupture de stock',                 3),
    (2, 'tension',                 'Tension d''approvisionnement',     2),
    (3, 'arret_commercialisation', 'Arrêt de commercialisation',       4),
    (4, 'remise_a_disposition',    'Remise à disposition',             1)
) AS s(code_statut, statut, libelle, gravite)
