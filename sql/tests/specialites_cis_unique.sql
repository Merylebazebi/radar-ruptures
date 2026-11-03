-- severite: erreur
-- Un CIS n'apparaît qu'une fois par snapshot dans le référentiel des spécialités.
SELECT date_snapshot, cis, count(*) AS nb
FROM staging.stg_specialites
GROUP BY date_snapshot, cis
HAVING count(*) > 1
