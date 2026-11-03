-- severite: erreur
-- Le jeu de ML a une ligne par signalement : pas de doublon (produit, statut, date de début).
SELECT id_produit, code_statut, count(*) AS nb
FROM marts.ml_signalements_ouverts
GROUP BY id_produit, code_statut, anciennete_jours
HAVING count(*) > 1
