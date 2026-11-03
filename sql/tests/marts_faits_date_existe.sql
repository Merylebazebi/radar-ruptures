-- severite: erreur
-- Chaque date de début et de snapshot existe dans la dimension date.
SELECT f.* FROM marts.fct_signalements f
LEFT JOIN marts.dim_date d1 ON d1.date = f.date_debut
LEFT JOIN marts.dim_date d2 ON d2.date = f.date_snapshot
WHERE (f.date_debut IS NOT NULL AND d1.date IS NULL) OR d2.date IS NULL
