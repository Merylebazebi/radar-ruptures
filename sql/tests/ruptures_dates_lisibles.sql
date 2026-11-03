-- severite: erreur
-- Une date présente dans le fichier doit être au format JJ/MM/AAAA, sinon elle serait perdue en staging.
SELECT * FROM raw.ruptures
WHERE (nullif(trim(date_debut), '') IS NOT NULL AND trim(date_debut) !~ '^\d{2}/\d{2}/\d{4}$')
   OR (nullif(trim(date_maj), '') IS NOT NULL AND trim(date_maj) !~ '^\d{2}/\d{2}/\d{4}$')
   OR (nullif(trim(date_remise_dispo), '') IS NOT NULL AND trim(date_remise_dispo) !~ '^\d{2}/\d{2}/\d{4}$')
