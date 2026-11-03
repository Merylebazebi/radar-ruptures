-- Vue de restitution pour le tableau de bord (Power BI) : un signalement ouvert par ligne
-- et par jour de scoring, avec le risque calculé par le modèle et de quoi agir.
-- Recréée par scoring.py après chaque scoring.
CREATE OR REPLACE VIEW marts.v_alertes AS
SELECT
    p.date_scoring,
    p.date_scoring = max(p.date_scoring) OVER ()          AS est_dernier_scoring,
    p.id_produit,
    p.cis,
    p.cip13,
    s.libelle                                             AS statut,
    coalesce(m.denomination, '(absent du référentiel)')   AS medicament,
    pr.libelle_presentation                               AS presentation,
    m.titulaires                                          AS laboratoire,
    m.est_mitm,
    coalesce(m.classe_atc_niveau1, 'inconnue')            AS classe_atc,
    greatest(m.nb_specialites_groupe - 1, 0)              AS nb_alternatives_generiques,
    p.proba_rupture,
    CASE
        WHEN p.proba_rupture >= 0.5 THEN '1 - élevé'
        WHEN p.proba_rupture >= 0.3 THEN '2 - moyen'
        ELSE '3 - faible'
    END                                                   AS niveau_risque,
    p.version_modele
FROM marts.predictions p
JOIN marts.dim_statut s ON s.code_statut = p.code_statut
LEFT JOIN marts.dim_medicament m ON m.cis = p.cis
LEFT JOIN marts.dim_presentation pr ON pr.cip13 = p.cip13
