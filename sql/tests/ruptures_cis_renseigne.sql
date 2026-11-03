-- severite: erreur
-- Chaque signalement doit porter un code CIS à 8 chiffres.
SELECT * FROM staging.stg_ruptures
WHERE cis IS NULL OR cis !~ '^\d{8}$'
