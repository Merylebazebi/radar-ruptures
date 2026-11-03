-- severite: avertissement
-- La remise à disposition ne devrait pas précéder le début de la rupture.
SELECT * FROM staging.stg_ruptures
WHERE date_remise_dispo < date_debut
