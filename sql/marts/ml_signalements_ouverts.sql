-- Jeu de données du modèle de ML : un signalement ouvert (tension ou rupture) par ligne,
-- au dernier snapshot, avec les caractéristiques du médicament connues à cette date.
-- Cible actuelle : cible_rupture (1 = rupture, 0 = tension), en attendant assez
-- d'historique pour la cible principale « passage de tension à rupture sous 30 jours ».
WITH dernier AS (
    SELECT max(date_snapshot) AS date_snapshot FROM marts.fct_signalements
),
signalements AS (
    SELECT f.*
    FROM marts.fct_signalements f
    JOIN dernier d USING (date_snapshot)
    WHERE f.code_statut IN (1, 2) AND f.est_en_cours
),
presentations_par_cis AS (
    SELECT
        cis,
        count(*)                          AS nb_presentations,
        bool_or(agrement_collectivites)   AS agrement_collectivites,
        max(taux_remboursement_pct)       AS taux_remboursement_max,
        avg(prix_avec_honoraires)         AS prix_moyen
    FROM marts.dim_presentation
    GROUP BY cis
),
pression_titulaire AS (
    -- Nombre de signalements ouverts chez le même titulaire : un laboratoire en difficulté
    -- sur un produit l'est souvent sur d'autres.
    SELECT m.titulaires, count(*) AS nb_signalements_titulaire
    FROM signalements s JOIN marts.dim_medicament m USING (cis)
    WHERE m.titulaires IS NOT NULL
    GROUP BY m.titulaires
)
SELECT
    -- Identifiants (non utilisés comme variables)
    s.id_produit,
    s.cis,
    s.cip13,
    s.date_snapshot,
    s.code_statut,
    -- Cible
    (s.code_statut = 1)::int                                   AS cible_rupture,
    -- Variables explicatives
    s.concerne_toute_la_specialite,
    s.duree_jours                                              AS anciennete_jours,
    m.dans_referentiel,
    m.est_mitm,
    coalesce(m.classe_atc_niveau1, 'inconnue')                 AS classe_atc_niveau1,
    coalesce(m.est_princeps, FALSE)                            AS est_princeps,
    m.id_groupe_generique IS NOT NULL                          AS a_un_groupe_generique,
    m.nb_specialites_groupe,
    coalesce(m.surveillance_renforcee, FALSE)                  AS surveillance_renforcee,
    coalesce(split_part(lower(m.forme_pharmaceutique), ' ', 1), 'inconnue') AS forme_simplifiee,
    coalesce(split_part(lower(m.voies_administration), ';', 1), 'inconnue') AS voie_principale,
    coalesce(p.nb_presentations, 0)                            AS nb_presentations,
    coalesce(p.agrement_collectivites, FALSE)                  AS agrement_collectivites,
    p.taux_remboursement_max,
    p.prix_moyen,
    coalesce(t.nb_signalements_titulaire, 1)                   AS nb_signalements_titulaire
FROM signalements s
JOIN marts.dim_medicament m USING (cis)
LEFT JOIN presentations_par_cis p USING (cis)
LEFT JOIN pression_titulaire t ON t.titulaires = m.titulaires
