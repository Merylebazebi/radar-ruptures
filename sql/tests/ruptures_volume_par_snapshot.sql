-- severite: erreur
-- Un snapshot avec moins de 100 signalements trahit un fichier tronqué ou mal téléchargé.
SELECT date_snapshot, count(*) AS nb_lignes
FROM staging.stg_ruptures
GROUP BY date_snapshot
HAVING count(*) < 100
