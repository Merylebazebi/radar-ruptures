-- severite: erreur
-- Un CIP13 n'apparaît qu'une fois par snapshot dans le référentiel des présentations.
SELECT date_snapshot, cip13, count(*) AS nb
FROM staging.stg_presentations
GROUP BY date_snapshot, cip13
HAVING count(*) > 1
