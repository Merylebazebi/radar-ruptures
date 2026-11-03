-- severite: erreur
-- La dimension médicament a exactement une ligne par CIS.
SELECT cis, count(*) AS nb FROM marts.dim_medicament GROUP BY cis HAVING count(*) > 1
