-- severite: erreur
-- Intégrité référentielle : chaque fait pointe vers un médicament de la dimension.
SELECT f.* FROM marts.fct_signalements f
LEFT JOIN marts.dim_medicament d ON d.cis = f.cis
WHERE d.cis IS NULL
