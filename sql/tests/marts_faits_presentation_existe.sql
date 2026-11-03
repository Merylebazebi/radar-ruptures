-- severite: avertissement
-- Le CIP13 d'un signalement devrait exister dans la dimension présentation
-- (un écart est possible pour une boîte retirée du référentiel).
SELECT f.* FROM marts.fct_signalements f
LEFT JOIN marts.dim_presentation p ON p.cip13 = f.cip13
WHERE f.cip13 IS NOT NULL AND p.cip13 IS NULL
