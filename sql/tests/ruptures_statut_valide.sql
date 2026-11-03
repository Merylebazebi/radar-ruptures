-- severite: erreur
-- Le code statut doit valoir 1 (rupture), 2 (tension), 3 (arrêt) ou 4 (remise à disposition).
SELECT * FROM staging.stg_ruptures
WHERE code_statut IS NULL OR code_statut NOT IN (1, 2, 3, 4)
