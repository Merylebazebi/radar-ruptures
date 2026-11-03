-- severite: erreur
-- La dimension présentation a exactement une ligne par CIP13.
SELECT cip13, count(*) AS nb FROM marts.dim_presentation GROUP BY cip13 HAVING count(*) > 1
