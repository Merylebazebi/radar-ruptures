-- severite: avertissement
-- Chaque CIS en rupture devrait exister dans le référentiel des spécialités
-- (un écart peut être légitime : médicament retiré du référentiel).
SELECT DISTINCT r.cis
FROM staging.stg_ruptures r
LEFT JOIN staging.stg_specialites s ON s.cis = r.cis
WHERE s.cis IS NULL
