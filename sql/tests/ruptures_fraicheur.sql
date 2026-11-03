-- severite: avertissement
-- Le dernier snapshot doit dater de moins de 3 jours, sinon l'ingestion quotidienne ne tourne plus.
SELECT max(date_snapshot) AS dernier_snapshot
FROM staging.stg_ruptures
HAVING max(date_snapshot) < current_date - 3
