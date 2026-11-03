-- severite: erreur
-- Intégrité référentielle : chaque fait pointe vers un statut connu.
SELECT f.* FROM marts.fct_signalements f
LEFT JOIN marts.dim_statut s ON s.code_statut = f.code_statut
WHERE s.code_statut IS NULL
