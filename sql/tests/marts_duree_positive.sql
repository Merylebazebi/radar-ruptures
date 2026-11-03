-- severite: avertissement
-- Une durée négative signale une date de début postérieure au snapshot (début annoncé
-- à l'avance, souvent un arrêt de commercialisation) ou à la remise : à surveiller.
SELECT * FROM marts.fct_signalements WHERE duree_jours < 0
